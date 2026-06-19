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
import re
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.ft_allocation_discipline import (
    ALLOCATION_DISCIPLINE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_basket_context_feature_bundle import (
    BASKET_MODEL_USE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_basket_structure_dependency import (
    BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS,
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
from state.promotions.feature_engineering.demand.ft_sparse_demand_noise import (
    SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_micro_market_equilibrium import (
    MICRO_MARKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_basket_equilibrium import (
    BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS,
)
from models.promotions.model_input_quality import (
    DOWNSTREAM_DECISION_SUPPORT_FEATURE_FAMILIES,
    STRICT_NUMERIC_KEY_COLUMNS,
    UNITS_HEAD_CORE_FEATURE_FAMILIES,
    build_model_input_quality_summary_text,
    classify_engineered_feature_role,
    classify_leakage_risk,
    filter_model_use_engineered_feature_columns,
    iter_review_only_engineered_feature_columns,
    iter_units_head_core_feature_columns,
)
from models.promotions.preprocessing import GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS
from state.promotions.datasets.dataset_assembler import (
    apply_governed_training_numeric_zero_fill_contract,
)
from state.promotions.datasets.dataset_validators import PromotionDatasetValidationError
from state.promotions.feature_engineering.registry import iter_registered_feature_modules
from state.promotions.feature_engineering.demand.probability import (
    PROBABILITY_MODEL_USE_FEATURE_COLUMNS,
    PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.stock.ft_target_stock_logic import (
    TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
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
    *TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
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
    # governed basket-structure and sparse-noise layer: first-class commercial support
    *BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS,
    *MICRO_MARKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS,
    *SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS,
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

TRAINING_DATA_SAMPLE_SCHEMA_COLUMNS: tuple[str, ...] = (
    "ordinal",
    "column_name",
    "source_dtype",
    "export_dtype",
    "column_role",
    "is_row_grain_column",
    "is_key_column",
    "is_engineered_feature",
    "is_model_use_engineered_feature",
    "is_review_only_engineered_feature",
    "is_target_column",
    "feature_family",
    "source_module",
    "null_count",
    "null_rate",
    "all_null_flag",
    "sample_value",
)

TRAINING_DATA_REQUIRED_IDENTITY_COLUMN_GROUPS: tuple[tuple[str, ...], ...] = (
    ("promotion_row_key",),
    ("store_number", "store_number_key"),
    ("promotion_header_key", "promotional_sku_id_key", "promotion_name"),
    ("sku_number", "sku_number_key"),
)

TRAINING_DATA_OPTIONAL_SKU_IDENTITY_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_number_key",
)

TRAINING_DATA_KNOWN_KEY_COLUMNS: tuple[str, ...] = (
    "promotion_row_key",
    "store_number",
    "store_number_key",
    "promotion_header_key",
    "sku_number",
    "sku_number_key",
    "promotional_sku_id",
    "promotional_sku_id_key",
)

TRAINING_DATA_NUMERIC_NAME_TOKENS: tuple[str, ...] = (
    "allocation",
    "amount",
    "avg",
    "baseline",
    "capital",
    "confidence",
    "cost",
    "count",
    "cover",
    "days",
    "demand",
    "depth",
    "discount",
    "dollar",
    "elasticity",
    "gm",
    "margin",
    "pct",
    "percent",
    "price",
    "probability",
    "profit",
    "qty",
    "quantity",
    "rate",
    "ratio",
    "response",
    "revenue",
    "risk",
    "sales",
    "score",
    "sell_through",
    "share",
    "soh",
    "stock",
    "support",
    "trend",
    "turnover",
    "unit",
    "uplift",
    "value",
    "velocity",
    "window",
)

TRAINING_DATA_TEXTUAL_SUFFIX_TOKENS: tuple[str, ...] = (
    "_reason",
    "_state",
    "_regime",
    "_posture",
    "_summary",
    "_source_column",
    "_source_table_name",
    "_table_name",
)

TRAINING_DATA_REQUESTED_FAMILY_ALIASES: tuple[dict[str, object], ...] = (
    {"requested_name": "allocation_discipline", "family_names": ("allocation_discipline",)},
    {"requested_name": "same_discount_history", "family_names": ("same_discount_promo_history",)},
    {"requested_name": "probability", "family_names": ("probability",)},
    {"requested_name": "target_stock_shape", "family_names": ("target_stock_shape",)},
    {"requested_name": "PCA", "family_names": ("pca",)},
    {"requested_name": "situational_awareness", "family_names": ("situational_awareness",)},
    {
        "requested_name": "fragility_opportunity_shape",
        "family_names": ("fragility_opportunity_shape", "fragility_opportunity"),
    },
    {
        "requested_name": "basket_equilibrium_or_transaction_object",
        "family_names": (
            "basket_context",
            "basket_structure_dependency",
            "micro_market_equilibrium",
        ),
    },
)

TRAINING_DATA_REQUIRED_NONNULL_MODEL_VISIBLE_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {*GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS}
)

_BOOL_TRUE_VALUES = {"1", "true", "yes", "y", "t"}
_BOOL_FALSE_VALUES = {"0", "false", "no", "n", "f"}
_DATE_LIKE_NAME_PATTERN = re.compile(r"(^|_)(date|datetime|timestamp|time|at)(_|$)", re.IGNORECASE)

FEATURE_DATASET_COVERAGE_AUDIT_COLUMNS: tuple[str, ...] = (
    "feature_name",
    "module_name",
    "registry_registered_flag",
    "present_in_training_ready_flag",
    "present_in_scoring_ready_flag",
    "present_in_model_use_flag",
    "review_only_flag",
    "recommended_action",
    "rationale",
)

MODEL_USE_FEATURE_COVERAGE_SUMMARY_COLUMNS: tuple[str, ...] = (
    "feature_family",
    "required_presence_scope",
    "feature_count",
    "present_in_training_ready_count",
    "present_in_scoring_ready_count",
    "present_in_model_use_count",
    "review_only_feature_count",
    "missing_model_use_feature_count",
    "review_only_model_use_leak_count",
    "family_status",
    "rationale",
)

FEATURE_FAMILY_SCOPE_MODEL_USE = "model_use"
FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY = "review_only_ready_dataset"
FEATURE_FAMILY_SCOPE_IF_PRESENT = "if_present"

MODEL_USE_FEATURE_FAMILY_REQUIREMENTS: tuple[dict[str, str], ...] = (
    {
        "feature_family": "basket_equilibrium",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_IF_PRESENT,
        "rationale": "Basket-equilibrium features are downstream decision-support context derived from prior-safe basket structure and should surface in diagnostics when present.",
    },
    {
        "feature_family": "basket_structure_dependency",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_MODEL_USE,
        "rationale": "Basket structure, anchor, drag-along, and dependency features are the governed cross-store generalisation layer.",
    },
    {
        "feature_family": "sparse_demand_noise",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_MODEL_USE,
        "rationale": "Sparse-demand and noise-regime features must reach model-use to distinguish stable low demand from random tail noise.",
    },
    {
        "feature_family": "micro_market_equilibrium",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_IF_PRESENT,
        "rationale": "Micro-market equilibrium features are downstream decision-support context and should surface in diagnostics when present without being required in the slim default units head.",
    },
    {
        "feature_family": "allocation_discipline",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_MODEL_USE,
        "rationale": "Trust-floor, allocation, and capital-discipline features must reach model-use unless explicitly governed review-only.",
    },
    {
        "feature_family": "same_discount_promo_history",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_MODEL_USE,
        "rationale": "Same-discount and prior-promotion memory are the governed commercial demand basis for train/score use.",
    },
    {
        "feature_family": "probability",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_MODEL_USE,
        "rationale": "The explicit probability model-use subset must be present while review-only probability diagnostics stay out.",
    },
    {
        "feature_family": "target_stock_shape",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_MODEL_USE,
        "rationale": "Period-aware target-stock shape features must be model-visible for trust-floor sizing.",
    },
    {
        "feature_family": "pca",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY,
        "rationale": "PCA interpretation layers must surface for analyst review and must not enter model-use.",
    },
    {
        "feature_family": "situational_awareness",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY,
        "rationale": "Situational-awareness interpretation layers must surface for analyst review and must not enter model-use.",
    },
    {
        "feature_family": "kalman_state",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY,
        "rationale": "Kalman-style demand-state diagnostics must surface for review first and must not enter model-use in this pass.",
    },
    {
        "feature_family": "distribution_shape_distance",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY,
        "rationale": "Distribution-distance diagnostics must surface for review first and must not enter model-use in this pass.",
    },
    {
        "feature_family": "fragility_opportunity",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY,
        "rationale": "Fragility-adjusted opportunity diagnostics are review-only until replay and audit evidence support promotion.",
    },
    {
        "feature_family": "dag_dependency_support",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY,
        "rationale": "DAG-informed support indicators are audit signals only and must not be treated as causal model-use proof.",
    },
    {
        "feature_family": "fragility_opportunity_shape",
        "required_presence_scope": FEATURE_FAMILY_SCOPE_IF_PRESENT,
        "rationale": "Fragility, opportunity, survival, and demand-shape layers are audited when present.",
    },
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
    feature_dataset_coverage_audit_csv_path: str
    model_use_feature_coverage_summary_csv_path: str
    model_use_feature_coverage_summary_json_path: str
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


@dataclass(frozen=True)
class PromotionTrainingDataSampleExportPaths:
    full_parquet_path: str
    sample_csv_path: str
    schema_csv_path: str
    quality_summary_json_path: str
    feature_coverage_audit_csv_path: str | None = None
    model_use_feature_coverage_summary_csv_path: str | None = None
    model_use_feature_coverage_summary_json_path: str | None = None
    feature_role_audit_csv_path: str | None = None
    feature_role_audit_summary_json_path: str | None = None
    core_head_candidate_review_csv_path: str | None = None
    core_head_candidate_review_summary_json_path: str | None = None


class PromotionFinalModelContractError(ValueError):
    """Raised when the final model-input frame violates the governed contract."""


class PromotionModelInputCsvExportError(ValueError):
    """Raised when the governed full CSV diagnosis export cannot be written safely."""


class PromotionTrainingDataExportError(ValueError):
    """Raised when a governed training-data inspection export cannot be written safely."""

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.details = dict(details or {})


def _trim_export_string_value(value: object) -> object:
    if value is None or pd.isna(value):
        return pd.NA
    trimmed = str(value).strip()
    return pd.NA if trimmed == "" else trimmed


def _trim_export_string_series(series: pd.Series) -> pd.Series:
    return series.map(_trim_export_string_value).astype(object)


def _looks_like_date_column(column_name: str, series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    return bool(_DATE_LIKE_NAME_PATTERN.search(column_name))


def _is_datetime_export_column(column_name: str, series: pd.Series, parsed: pd.Series) -> bool:
    lowered = column_name.lower()
    if any(token in lowered for token in ("datetime", "timestamp", "_at")):
        return True
    if not pd.api.types.is_datetime64_any_dtype(series):
        return False
    non_null = parsed.dropna()
    if non_null.empty:
        return False
    return bool(
        non_null.dt.hour.ne(0).any()
        or non_null.dt.minute.ne(0).any()
        or non_null.dt.second.ne(0).any()
        or non_null.dt.microsecond.ne(0).any()
    )


def _format_temporal_series_for_export(
    parsed: pd.Series,
    *,
    include_time: bool,
) -> pd.Series:
    formatted = pd.Series(pd.NA, index=parsed.index, dtype=object)
    non_null = parsed.notna()
    if not bool(non_null.any()):
        return formatted
    values = parsed.loc[non_null]
    if include_time:
        formatted.loc[non_null] = values.map(lambda value: value.isoformat())
    else:
        formatted.loc[non_null] = values.dt.strftime("%Y-%m-%d")
    return formatted


def _is_flag_column(column_name: str, series: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(series):
        return True
    lowered = column_name.lower()
    return lowered.endswith("_flag") or lowered.startswith("is_")


def _series_sample_values(series: pd.Series, *, limit: int = 5) -> list[str]:
    if series.empty:
        return []
    return [str(value) for value in series.dropna().drop_duplicates().head(limit).tolist()]


def _normalize_flag_series(
    series: pd.Series,
    *,
    column_name: str,
) -> tuple[pd.Series, dict[str, object] | None]:
    if pd.api.types.is_bool_dtype(series):
        return series.astype("Int64"), None
    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        invalid_mask = series.notna() & ~numeric.isin([0, 1])
        if bool(invalid_mask.any()):
            return series, {
                "column_name": column_name,
                "reason": "flag_column_contains_non_boolean_numeric_values",
                "sample_invalid_values": _series_sample_values(series.loc[invalid_mask]),
            }
        return numeric.astype("Int64"), None

    trimmed = _trim_export_string_series(series)
    normalized = trimmed.astype("string").str.lower()
    numeric = pd.to_numeric(trimmed, errors="coerce")
    valid_mask = normalized.isin(_BOOL_TRUE_VALUES | _BOOL_FALSE_VALUES) | numeric.isin([0, 1])
    invalid_mask = trimmed.notna() & ~valid_mask
    if bool(invalid_mask.any()):
        return trimmed, {
            "column_name": column_name,
            "reason": "flag_column_contains_non_boolean_values",
            "sample_invalid_values": _series_sample_values(trimmed.loc[invalid_mask]),
        }
    output = pd.Series(pd.NA, index=trimmed.index, dtype="Int64")
    output.loc[normalized.isin(_BOOL_TRUE_VALUES)] = 1
    output.loc[normalized.isin(_BOOL_FALSE_VALUES)] = 0
    numeric_bool_mask = trimmed.notna() & numeric.isin([0, 1])
    if bool(numeric_bool_mask.any()):
        output.loc[numeric_bool_mask] = numeric.loc[numeric_bool_mask].astype("Int64")
    return output, None


def _column_expected_numeric(
    column_name: str,
    *,
    feature_columns: set[str],
    target_columns: set[str],
) -> bool:
    if column_name in STRICT_NUMERIC_KEY_COLUMNS:
        return True
    lowered = column_name.lower()
    if _DATE_LIKE_NAME_PATTERN.search(lowered):
        return False
    if any(lowered.endswith(token) for token in TRAINING_DATA_TEXTUAL_SUFFIX_TOKENS):
        return False
    if lowered.endswith("_flag") or lowered.startswith("is_"):
        return True
    return any(token in lowered for token in TRAINING_DATA_NUMERIC_NAME_TOKENS)


def _coerce_expected_numeric_series(
    series: pd.Series,
    *,
    column_name: str,
    strict_integer: bool,
) -> tuple[pd.Series, dict[str, object] | None, dict[str, object] | None]:
    trimmed = _trim_export_string_series(series)
    coerced = pd.to_numeric(trimmed, errors="coerce")
    non_null_mask = trimmed.notna()
    numeric_like_mask = non_null_mask & coerced.notna()
    nonnumeric_like_mask = non_null_mask & coerced.isna()

    mixed_type_issue: dict[str, object] | None = None
    coercion_failure: dict[str, object] | None = None
    if bool(numeric_like_mask.any() and nonnumeric_like_mask.any()):
        mixed_type_issue = {
            "column_name": column_name,
            "numeric_like_count": int(numeric_like_mask.sum()),
            "nonnumeric_like_count": int(nonnumeric_like_mask.sum()),
            "sample_nonnumeric_values": _series_sample_values(trimmed.loc[nonnumeric_like_mask]),
        }
    elif bool(nonnumeric_like_mask.any()):
        coercion_failure = {
            "column_name": column_name,
            "reason": "expected_numeric_column_contains_non_numeric_values",
            "sample_invalid_values": _series_sample_values(trimmed.loc[nonnumeric_like_mask]),
        }

    if coercion_failure is None and strict_integer:
        non_integer_mask = non_null_mask & coerced.notna() & coerced.mod(1).ne(0)
        if bool(non_integer_mask.any()):
            coercion_failure = {
                "column_name": column_name,
                "reason": "strict_numeric_key_contains_non_integer_values",
                "sample_invalid_values": _series_sample_values(trimmed.loc[non_integer_mask]),
            }

    if mixed_type_issue is not None or coercion_failure is not None:
        return trimmed, mixed_type_issue, coercion_failure

    non_null = coerced.dropna()
    if non_null.empty:
        dtype = "Int64" if strict_integer else "Float64"
        return pd.Series(pd.NA, index=trimmed.index, dtype=dtype), None, None
    if strict_integer or bool(non_null.mod(1).eq(0).all()):
        return coerced.round(0).astype("Int64"), None, None
    return coerced.astype("float64"), None, None


def _numeric_columns_with_excess_precision(
    numeric_columns: Mapping[str, pd.Series],
    *,
    decimals: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    tolerance = 10 ** (-(decimals + 2))
    for column_name, series in numeric_columns.items():
        numeric = pd.to_numeric(series, errors="coerce")
        non_null = numeric.dropna()
        if non_null.empty or bool(non_null.mod(1).eq(0).all()):
            continue
        diff = (non_null.astype(float) - non_null.astype(float).round(decimals)).abs()
        offending = diff > tolerance
        if not bool(offending.any()):
            continue
        rows.append(
            {
                "column_name": column_name,
                "offending_row_count": int(offending.sum()),
                "sample_values": [float(value) for value in non_null.loc[offending].head(5).tolist()],
            }
        )
    return rows


def _numeric_min_max_summary(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for column_name in frame.columns:
        series = frame[column_name]
        if not pd.api.types.is_numeric_dtype(series):
            continue
        non_null = series.dropna()
        if non_null.empty:
            continue
        min_value = non_null.min()
        max_value = non_null.max()
        summary[str(column_name)] = {
            "min": _json_scalar(min_value),
            "max": _json_scalar(max_value),
        }
    return summary


def _json_scalar(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return round(float(value), NUMERIC_EXPORT_DECIMALS)
    return str(value)


def _required_training_identity_columns(columns: Sequence[str]) -> tuple[list[str], list[str]]:
    column_set = {str(column_name) for column_name in columns}
    selected_required_columns: list[str] = []
    missing: list[str] = []
    for column_group in TRAINING_DATA_REQUIRED_IDENTITY_COLUMN_GROUPS:
        present = [column_name for column_name in column_group if column_name in column_set]
        if present:
            selected_required_columns.append(present[0])
        else:
            missing.append("_or_".join(column_group))
    present_keys = [
        column_name
        for column_name in TRAINING_DATA_KNOWN_KEY_COLUMNS
        if column_name in column_set
    ]
    present_keys = list(dict.fromkeys([*selected_required_columns, *present_keys]))
    return missing, present_keys


def _present_required_training_identity_columns(columns: Sequence[str]) -> list[str]:
    column_set = {str(column_name) for column_name in columns}
    selected_required_columns: list[str] = []
    for column_group in TRAINING_DATA_REQUIRED_IDENTITY_COLUMN_GROUPS:
        present = [column_name for column_name in column_group if column_name in column_set]
        if present:
            selected_required_columns.append(present[0])
    return selected_required_columns


def _training_feature_family_summary(
    *,
    engineered_feature_columns: Sequence[str],
) -> list[dict[str, object]]:
    module_by_feature = _registered_feature_module_by_column()
    review_only_features = set(iter_review_only_engineered_feature_columns())
    present_features = {
        str(column_name)
        for column_name in engineered_feature_columns
        if str(column_name).startswith(ENGINEERED_FEATURE_PREFIX)
    }
    relevant_feature_names = sorted(set(module_by_feature) | present_features)
    feature_family_by_name = {
        feature_name: _feature_family_for_coverage_row(feature_name, module_by_feature.get(feature_name, ""))
        for feature_name in relevant_feature_names
    }
    family_names = [row["feature_family"] for row in MODEL_USE_FEATURE_FAMILY_REQUIREMENTS]
    family_names.extend(
        family_name
        for family_name in sorted(set(feature_family_by_name.values()))
        if family_name not in set(family_names)
    )
    rows: list[dict[str, object]] = []
    for family_name in family_names:
        family_feature_names = [
            feature_name
            for feature_name, classified_family in feature_family_by_name.items()
            if classified_family == family_name
        ]
        registered_feature_names = [
            feature_name for feature_name in family_feature_names if feature_name in module_by_feature
        ]
        present_feature_names = [
            feature_name for feature_name in family_feature_names if feature_name in present_features
        ]
        present_model_use_feature_names = [
            feature_name for feature_name in present_feature_names if feature_name not in review_only_features
        ]
        present_review_only_feature_names = [
            feature_name for feature_name in present_feature_names if feature_name in review_only_features
        ]
        missing_registered_model_use_feature_names = [
            feature_name
            for feature_name in registered_feature_names
            if feature_name not in review_only_features and feature_name not in present_features
        ]
        missing_registered_review_only_feature_names = [
            feature_name
            for feature_name in registered_feature_names
            if feature_name in review_only_features and feature_name not in present_features
        ]
        if not registered_feature_names:
            family_status = "not_registered"
        elif not present_feature_names:
            family_status = "missing_from_training_dataset"
        elif present_model_use_feature_names and present_review_only_feature_names:
            family_status = "model_use_and_review_only_present"
        elif present_model_use_feature_names:
            family_status = "model_use_present"
        elif present_review_only_feature_names:
            family_status = "review_only_present"
        else:
            family_status = "present_unclassified"
        rows.append(
            {
                "feature_family": family_name,
                "registered_feature_count": int(len(registered_feature_names)),
                "present_feature_count": int(len(present_feature_names)),
                "present_model_use_feature_count": int(len(present_model_use_feature_names)),
                "present_review_only_feature_count": int(len(present_review_only_feature_names)),
                "missing_registered_model_use_feature_names": missing_registered_model_use_feature_names,
                "missing_registered_review_only_feature_names": missing_registered_review_only_feature_names,
                "present_feature_names": present_feature_names,
                "family_status": family_status,
            }
        )
    return rows


def _requested_training_family_visibility(
    family_rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    family_rows_by_name = {str(row["feature_family"]): row for row in family_rows}
    family_requirements = {
        str(row["feature_family"]): str(row["required_presence_scope"])
        for row in MODEL_USE_FEATURE_FAMILY_REQUIREMENTS
    }
    visibility: dict[str, dict[str, object]] = {}
    for mapping in TRAINING_DATA_REQUESTED_FAMILY_ALIASES:
        requested_name = str(mapping["requested_name"])
        family_names = tuple(str(name) for name in mapping["family_names"])
        matched_rows = [family_rows_by_name[name] for name in family_names if name in family_rows_by_name]
        registered_feature_count = int(
            sum(int(row.get("registered_feature_count", 0)) for row in matched_rows)
        )
        present_feature_count = int(
            sum(int(row.get("present_feature_count", 0)) for row in matched_rows)
        )
        present_families = [
            str(row["feature_family"])
            for row in matched_rows
            if int(row.get("present_feature_count", 0)) > 0
        ]
        review_only_policy_exclusion = (
            bool(matched_rows)
            and present_feature_count == 0
            and all(
                family_requirements.get(str(row["feature_family"])) == FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY
                for row in matched_rows
            )
        )
        if registered_feature_count == 0:
            status = "not_registered"
        elif review_only_policy_exclusion:
            status = "review_only_excluded_by_policy"
        elif present_feature_count > 0:
            status = "present"
        else:
            status = "missing"
        visibility[requested_name] = {
            "status": status,
            "matched_families": list(family_names),
            "present_families": present_families,
            "registered_feature_count": registered_feature_count,
            "present_feature_count": present_feature_count,
        }
    return visibility


def _feature_role_label(column_name: str) -> str:
    """Return the governed role label for one training-dataset column."""

    if column_name.startswith(ENGINEERED_FEATURE_PREFIX):
        role = classify_engineered_feature_role(column_name)
        if role == "review_only":
            return "review_only_diagnostic"
        return str(role)
    if column_name.startswith(TARGET_COLUMN_PREFIX):
        return "target_or_realised_audit"
    leakage = classify_leakage_risk(column_name)
    if leakage is not None and leakage[0] != "audit_only":
        return "target_or_realised_audit"
    return "non_feature_or_metadata"


def _build_feature_role_audit_frame(
    *,
    original_frame: pd.DataFrame,
    ml_ready_frame: pd.DataFrame,
    feature_columns: Sequence[str],
    target_columns: Sequence[str],
    zero_fill_summary: Mapping[str, object],
) -> pd.DataFrame:
    """Return column-level role and missingness audit rows for training data."""

    role_rows: list[dict[str, object]] = []
    module_by_feature = _registered_feature_module_by_column()
    feature_column_set = set(str(column_name) for column_name in feature_columns)
    target_column_set = set(str(column_name) for column_name in target_columns)
    zero_fill_rows_by_column = {
        str(row["column_name"]): row
        for row in zero_fill_summary.get("column_rows", [])
    }
    single_store_slice = bool(
        "store_number" in ml_ready_frame.columns
        and ml_ready_frame["store_number"].dropna().astype(str).nunique() <= 1
    )
    candidate_columns = [
        str(column_name)
        for column_name in original_frame.columns
        if _feature_role_label(str(column_name)) != "non_feature_or_metadata"
    ]
    for column_name in candidate_columns:
        role = _feature_role_label(column_name)
        source_series = original_frame[column_name]
        ml_ready_series = ml_ready_frame[column_name]
        zero_fill_row = zero_fill_rows_by_column.get(column_name, {})
        pre_null_count = int(zero_fill_row.get("pre_zero_fill_null_count", int(source_series.isna().sum())))
        post_null_count = int(zero_fill_row.get("post_zero_fill_null_count", int(ml_ready_series.isna().sum())))
        zero_filled_count = int(zero_fill_row.get("zero_filled_count", 0))
        feature_family = (
            _feature_family_for_coverage_row(column_name, module_by_feature.get(column_name, ""))
            if column_name in feature_column_set
            else "target_or_realised_audit"
        )
        non_null = ml_ready_series.dropna()
        unique_count = int(non_null.nunique(dropna=True))
        constant_flag = bool(len(non_null.index) > 0 and unique_count <= 1)
        if constant_flag:
            constant_behavior_class = (
                "constant_single_store_slice"
                if single_store_slice
                else "constant_multi_store_or_structural"
            )
        else:
            constant_behavior_class = "non_constant"
        role_rows.append(
            {
                "column_name": column_name,
                "feature_family": feature_family,
                "feature_role": role,
                "source_dtype": str(source_series.dtype),
                "ml_ready_dtype": str(ml_ready_series.dtype),
                "pre_zero_fill_null_count": pre_null_count,
                "pre_zero_fill_null_rate": round(float(pre_null_count / max(len(source_series.index), 1)), 6),
                "post_zero_fill_null_count": post_null_count,
                "post_zero_fill_null_rate": round(float(post_null_count / max(len(ml_ready_series.index), 1)), 6),
                "zero_filled_count": zero_filled_count,
                "structurally_unavailable_count": int(zero_fill_row.get("structurally_unavailable_count", 0)),
                "insufficient_history_count": int(zero_fill_row.get("insufficient_history_count", 0)),
                "unclassified_missingness_count": int(zero_fill_row.get("unclassified_missingness_count", 0)),
                "constant_flag": constant_flag,
                "constant_behavior_class": constant_behavior_class,
                "selected_for_training_contract_flag": column_name in feature_column_set or column_name in target_column_set,
            }
        )
    return pd.DataFrame(role_rows)


def _build_feature_role_audit_summary(
    *,
    role_audit_frame: pd.DataFrame,
    zero_fill_summary: Mapping[str, object],
) -> dict[str, object]:
    """Return aggregate role, null-burden, and constant-burden diagnostics."""

    summary_by_role: dict[str, dict[str, object]] = {}
    for role_name, group in role_audit_frame.groupby("feature_role", dropna=False):
        row_count = max(int(len(group.index)), 1)
        summary_by_role[str(role_name)] = {
            "column_count": int(len(group.index)),
            "pre_zero_fill_null_count": int(group["pre_zero_fill_null_count"].sum()),
            "pre_zero_fill_null_rate": round(float(group["pre_zero_fill_null_count"].sum() / row_count), 6),
            "post_zero_fill_null_count": int(group["post_zero_fill_null_count"].sum()),
            "post_zero_fill_null_rate": round(float(group["post_zero_fill_null_count"].sum() / row_count), 6),
            "zero_filled_cell_count": int(group["zero_filled_count"].sum()),
            "constant_column_count": int(group["constant_flag"].astype(bool).sum()),
            "constant_column_rate": round(float(group["constant_flag"].astype(bool).mean()), 6),
            "feature_families": sorted(group["feature_family"].astype(str).unique().tolist()),
        }

    return {
        "role_counts": {key: int(value["column_count"]) for key, value in summary_by_role.items()},
        "role_summary": summary_by_role,
        "numeric_zero_fill_summary": zero_fill_summary,
        "columns_intentionally_left_nullable": list(zero_fill_summary.get("columns_intentionally_left_nullable", [])),
        "columns_excluded_from_zero_fill_non_numeric": list(zero_fill_summary.get("columns_excluded_from_zero_fill_non_numeric", [])),
        "invalid_numeric_coercion_cases": list(zero_fill_summary.get("invalid_numeric_coercion_cases", [])),
    }


def _build_core_head_candidate_review_frame(
    *,
    role_audit_frame: pd.DataFrame,
    family_rows: Sequence[Mapping[str, object]],
) -> pd.DataFrame:
    """Return advisory family ranking rows for units-head suitability."""

    family_status_by_name = {
        str(row["feature_family"]): str(row["family_status"])
        for row in family_rows
    }
    rows: list[dict[str, object]] = []
    feature_roles = role_audit_frame.loc[
        role_audit_frame["feature_role"].astype(str) != "target_or_realised_audit"
    ]
    for family_name, group in feature_roles.groupby("feature_family", dropna=False):
        family_name = str(family_name)
        if family_name == "target_or_realised_audit":
            continue
        role_candidates = group["feature_role"].astype(str)
        if role_candidates.eq("units_head_core").any():
            role = "units_head_core"
        elif role_candidates.eq("review_only_diagnostic").any():
            role = "review_only_diagnostic"
        else:
            role = "downstream_decision_support"
        if family_status_by_name.get(family_name) in {"missing_from_training_dataset", "not_registered"}:
            recommendation_label = "remove_from_default_head"
        elif role == "units_head_core":
            recommendation_label = "keep_core"
        elif role == "review_only_diagnostic":
            recommendation_label = "review_only"
        else:
            recommendation_label = "keep_downstream_only"
        rows.append(
            {
                "feature_family": family_name,
                "feature_role": role,
                "feature_count": int(len(group.index)),
                "mean_pre_zero_fill_null_rate": round(float(group["pre_zero_fill_null_rate"].mean()), 6),
                "mean_post_zero_fill_null_rate": round(float(group["post_zero_fill_null_rate"].mean()), 6),
                "zero_filled_cell_count": int(group["zero_filled_count"].sum()),
                "constant_feature_count": int(group["constant_flag"].astype(bool).sum()),
                "constant_feature_rate": round(float(group["constant_flag"].astype(bool).mean()), 6),
                "family_status": family_status_by_name.get(family_name, "unknown"),
                "ablation_evidence_status": (
                    "approved_units_head_core_contract"
                    if family_name in UNITS_HEAD_CORE_FEATURE_FAMILIES
                    else "approved_downstream_only_contract"
                    if family_name in DOWNSTREAM_DECISION_SUPPORT_FEATURE_FAMILIES
                    else "not_attached_in_training_export"
                ),
                "recommendation_label": recommendation_label,
            }
        )
    return pd.DataFrame(rows).sort_values(["feature_role", "feature_family"]).reset_index(drop=True)


def _build_core_head_candidate_review_summary(
    *,
    review_frame: pd.DataFrame,
) -> dict[str, object]:
    """Return aggregate counts for advisory core-head review labels."""

    if review_frame.empty:
        return {
            "recommendation_counts": {},
            "families_by_recommendation": {},
        }
    return {
        "recommendation_counts": {
            str(label): int(count)
            for label, count in review_frame["recommendation_label"].astype(str).value_counts().sort_index().items()
        },
        "families_by_recommendation": {
            str(label): sorted(group["feature_family"].astype(str).tolist())
            for label, group in review_frame.groupby("recommendation_label", dropna=False)
        },
    }


def _training_feature_manifest_comparison(
    *,
    current_feature_columns: Sequence[str],
    prior_feature_columns: Sequence[str],
) -> dict[str, object]:
    current_features = {
        str(column_name)
        for column_name in current_feature_columns
        if str(column_name).startswith(ENGINEERED_FEATURE_PREFIX)
    }
    prior_features = {
        str(column_name)
        for column_name in prior_feature_columns
        if str(column_name).startswith(ENGINEERED_FEATURE_PREFIX)
    }
    module_by_feature = _registered_feature_module_by_column()

    def _families(feature_names: set[str]) -> list[str]:
        return sorted(
            {
                _feature_family_for_coverage_row(feature_name, module_by_feature.get(feature_name, ""))
                for feature_name in feature_names
            }
        )

    def _modules(feature_names: set[str]) -> list[str]:
        return sorted(
            {
                module_by_feature[feature_name]
                for feature_name in feature_names
                if feature_name in module_by_feature and str(module_by_feature[feature_name]).strip()
            }
        )

    new_features = current_features - prior_features
    removed_features = prior_features - current_features
    return {
        "prior_feature_count": int(len(prior_features)),
        "current_feature_count": int(len(current_features)),
        "new_feature_columns_since_prior_build": sorted(new_features),
        "removed_feature_columns_since_prior_build": sorted(removed_features),
        "new_feature_families_since_prior_build": _families(new_features),
        "removed_feature_families_since_prior_build": _families(removed_features),
        "new_ft_modules_since_prior_build": _modules(new_features),
        "removed_ft_modules_since_prior_build": _modules(removed_features),
    }


def _build_training_data_sample_schema(
    *,
    source_frame: pd.DataFrame,
    export_frame: pd.DataFrame,
    key_columns: Sequence[str],
    feature_columns: Sequence[str],
    target_columns: Sequence[str],
) -> pd.DataFrame:
    feature_column_set = set(feature_columns)
    target_column_set = set(target_columns)
    key_column_set = set(key_columns)
    module_by_feature = _registered_feature_module_by_column()
    review_only_features = set(iter_review_only_engineered_feature_columns())
    row_count = max(int(len(source_frame.index)), 1)
    rows: list[dict[str, object]] = []
    for ordinal, column_name in enumerate(source_frame.columns, start=1):
        source_series = source_frame[column_name]
        export_series = export_frame[column_name]
        non_null = source_series.dropna()
        sample_value = "" if non_null.empty else str(non_null.iloc[0])[:120]
        column_role = "raw_input"
        if column_name == "promotion_row_key":
            column_role = "row_grain"
        elif column_name in target_column_set:
            column_role = "target"
        elif column_name in feature_column_set:
            column_role = "engineered_feature"
        elif column_name in key_column_set:
            column_role = "key"
        rows.append(
            {
                "ordinal": ordinal,
                "column_name": str(column_name),
                "source_dtype": str(source_series.dtype),
                "export_dtype": str(export_series.dtype),
                "column_role": column_role,
                "is_row_grain_column": bool(column_name == "promotion_row_key"),
                "is_key_column": bool(column_name in key_column_set),
                "is_engineered_feature": bool(column_name in feature_column_set),
                "is_model_use_engineered_feature": bool(
                    column_name in feature_column_set and column_name not in review_only_features
                ),
                "is_review_only_engineered_feature": bool(column_name in review_only_features),
                "is_target_column": bool(column_name in target_column_set),
                "feature_family": (
                    _feature_family_for_coverage_row(str(column_name), module_by_feature.get(str(column_name), ""))
                    if column_name in feature_column_set
                    else ""
                ),
                "source_module": module_by_feature.get(str(column_name), ""),
                "null_count": int(source_series.isna().sum()),
                "null_rate": round(float(source_series.isna().sum() / row_count), 6),
                "all_null_flag": bool(source_series.isna().all()),
                "sample_value": sample_value,
            }
        )
    return pd.DataFrame(rows, columns=TRAINING_DATA_SAMPLE_SCHEMA_COLUMNS)


def write_training_data_sample_artifacts(
    *,
    run_id: str,
    dataset_frame: pd.DataFrame,
    output_root: str | Path,
    source_dataset_path: str | Path | None = None,
    source_manifest_path: str | Path | None = None,
    row_limit: int = INSPECTION_SAMPLE_ROWS,
    feature_columns: Sequence[str] | None = None,
    target_columns: Sequence[str] | None = None,
    prior_feature_columns: Sequence[str] | None = None,
) -> PromotionTrainingDataSampleExportPaths:
    """Write a governed inspection export for the assembled training dataset."""

    if row_limit <= 0:
        raise ValueError(f"row_limit must be > 0, got {row_limit}")

    feature_column_names = tuple(
        str(column_name)
        for column_name in (feature_columns or tuple(column_name for column_name in dataset_frame.columns if str(column_name).startswith(ENGINEERED_FEATURE_PREFIX)))
    )
    target_column_names = tuple(
        str(column_name)
        for column_name in (target_columns or tuple(column_name for column_name in dataset_frame.columns if str(column_name).startswith(TARGET_COLUMN_PREFIX)))
    )
    original_dataset_frame = dataset_frame.copy()
    try:
        ml_ready_dataset_frame, export_zero_fill_summary = apply_governed_training_numeric_zero_fill_contract(
            dataset_frame,
            feature_columns=feature_column_names,
            target_columns=target_column_names,
        )
    except PromotionDatasetValidationError as error:
        raise PromotionTrainingDataExportError(
            "Training-data inspection export failed validation.",
            details=error.details,
        ) from error

    upstream_zero_fill_summary: dict[str, object] | None = None
    if source_manifest_path is not None and Path(source_manifest_path).exists():
        try:
            manifest_payload = json.loads(Path(source_manifest_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest_payload = {}
        upstream_payload = manifest_payload.get("governed_numeric_zero_fill_summary")
        if isinstance(upstream_payload, dict):
            upstream_zero_fill_summary = upstream_payload

    feature_column_set = set(feature_column_names)
    target_column_set = set(target_column_names)
    missing_identity_columns, key_columns = _required_training_identity_columns(tuple(ml_ready_dataset_frame.columns))
    missing_feature_columns = [
        column_name for column_name in feature_column_names if column_name not in set(ml_ready_dataset_frame.columns)
    ]
    missing_target_columns = [
        column_name for column_name in target_column_names if column_name not in set(ml_ready_dataset_frame.columns)
    ]

    working = ml_ready_dataset_frame.copy()
    export_frame = pd.DataFrame(index=working.index)
    mixed_type_columns: list[dict[str, object]] = []
    numeric_coercion_failures: list[dict[str, object]] = []
    invalid_date_columns: list[dict[str, object]] = []
    numeric_columns_for_precision: dict[str, pd.Series] = {}

    for column_name in working.columns:
        series = working[column_name]
        export_series = series.copy()
        if (
            pd.api.types.is_object_dtype(export_series)
            or pd.api.types.is_string_dtype(export_series)
            or isinstance(export_series.dtype, pd.CategoricalDtype)
        ):
            export_series = _trim_export_string_series(export_series)

        if _looks_like_date_column(str(column_name), export_series):
            parsed = pd.to_datetime(export_series, errors="coerce")
            invalid_mask = export_series.notna() & parsed.isna()
            if bool(invalid_mask.any()):
                invalid_date_columns.append(
                    {
                        "column_name": str(column_name),
                        "invalid_row_count": int(invalid_mask.sum()),
                        "sample_invalid_values": _series_sample_values(export_series.loc[invalid_mask]),
                    }
                )
            include_time = _is_datetime_export_column(str(column_name), series, parsed)
            export_frame[column_name] = _format_temporal_series_for_export(parsed, include_time=include_time)
            continue

        if _is_flag_column(str(column_name), export_series):
            normalized_flag, flag_failure = _normalize_flag_series(export_series, column_name=str(column_name))
            if flag_failure is not None:
                numeric_coercion_failures.append(flag_failure)
            export_frame[column_name] = normalized_flag
            continue

        if pd.api.types.is_bool_dtype(export_series):
            export_frame[column_name] = export_series.astype("Int64")
            continue

        if pd.api.types.is_numeric_dtype(export_series):
            export_frame[column_name] = export_series
            numeric_columns_for_precision[str(column_name)] = pd.to_numeric(export_series, errors="coerce")
            continue

        if _column_expected_numeric(
            str(column_name),
            feature_columns=feature_column_set,
            target_columns=target_column_set,
        ):
            coerced_series, mixed_issue, coercion_failure = _coerce_expected_numeric_series(
                export_series,
                column_name=str(column_name),
                strict_integer=str(column_name) in STRICT_NUMERIC_KEY_COLUMNS,
            )
            if mixed_issue is not None:
                mixed_type_columns.append(mixed_issue)
            if coercion_failure is not None:
                numeric_coercion_failures.append(coercion_failure)
            export_frame[column_name] = coerced_series
            if pd.api.types.is_numeric_dtype(coerced_series):
                numeric_columns_for_precision[str(column_name)] = pd.to_numeric(coerced_series, errors="coerce")
            continue

        export_frame[column_name] = export_series

    required_non_null_columns = _present_required_training_identity_columns(export_frame.columns)

    required_non_null_failures = [
        {
            "column_name": column_name,
            "null_count": int(export_frame[column_name].isna().sum()),
        }
        for column_name in required_non_null_columns
        if bool(export_frame[column_name].isna().any())
    ]
    all_null_columns = [
        str(column_name)
        for column_name in export_frame.columns
        if bool(export_frame[column_name].isna().all())
    ]
    review_only_features = set(iter_review_only_engineered_feature_columns())
    unexpected_all_null_columns = [
        column_name
        for column_name in all_null_columns
        if column_name in required_non_null_columns
        or column_name in target_column_set
        or (
            column_name in feature_column_set
            and column_name in TRAINING_DATA_REQUIRED_NONNULL_MODEL_VISIBLE_FEATURE_COLUMNS
            and column_name not in review_only_features
        )
    ]
    if (
        "feature_uplift_allocation_discipline_score" in all_null_columns
        and _uplift_allocation_score_support_rows_present(export_frame)
    ):
        unexpected_all_null_columns.append("feature_uplift_allocation_discipline_score")
    unexpected_all_null_columns = list(dict.fromkeys(unexpected_all_null_columns))

    precision_rows = _numeric_columns_with_excess_precision(
        numeric_columns_for_precision,
        decimals=NUMERIC_EXPORT_DECIMALS,
    )

    validation_details = {
        "missing_identity_columns": missing_identity_columns,
        "missing_feature_columns": missing_feature_columns,
        "missing_target_columns": missing_target_columns,
        "mixed_type_columns": mixed_type_columns,
        "numeric_coercion_failures": numeric_coercion_failures,
        "invalid_date_columns": invalid_date_columns,
        "required_non_null_failures": required_non_null_failures,
        "unexpected_all_null_columns": unexpected_all_null_columns,
    }
    has_fatal_issues = any(
        bool(validation_details[key])
        for key in (
            "missing_identity_columns",
            "missing_feature_columns",
            "missing_target_columns",
            "mixed_type_columns",
            "numeric_coercion_failures",
            "invalid_date_columns",
            "required_non_null_failures",
            "unexpected_all_null_columns",
        )
    )
    if has_fatal_issues:
        raise PromotionTrainingDataExportError(
            "Training-data inspection export failed validation.",
            details=validation_details,
        )

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    full_parquet_path = root / "training_data_full.parquet"
    sample_csv_path = root / f"training_data_sample_top_{int(row_limit)}.csv"
    schema_csv_path = root / "training_data_sample_schema.csv"
    quality_summary_json_path = root / "training_data_sample_quality_summary.json"
    feature_coverage_audit_csv_path = root / "training_dataset_feature_coverage_audit.csv"
    model_use_feature_coverage_summary_csv_path = root / "training_dataset_model_use_feature_coverage_summary.csv"
    model_use_feature_coverage_summary_json_path = root / "training_dataset_model_use_feature_coverage_summary.json"
    feature_role_audit_csv_path = root / "feature_role_audit.csv"
    feature_role_audit_summary_json_path = root / "feature_role_audit_summary.json"
    core_head_candidate_review_csv_path = root / "core_head_candidate_review.csv"
    core_head_candidate_review_summary_json_path = root / "core_head_candidate_review_summary.json"

    working.to_parquet(full_parquet_path, index=False)
    rounded_sample = _round_for_export(export_frame.head(row_limit), decimals=NUMERIC_EXPORT_DECIMALS)
    rounded_sample.to_csv(sample_csv_path, index=False)

    schema_frame = _build_training_data_sample_schema(
        source_frame=working,
        export_frame=export_frame,
        key_columns=key_columns,
        feature_columns=feature_column_names,
        target_columns=target_column_names,
    )
    schema_frame.to_csv(schema_csv_path, index=False)

    model_use_feature_column_names = filter_model_use_engineered_feature_columns(feature_column_names)
    feature_coverage_audit_frame = _build_feature_dataset_coverage_audit(
        stage_label="training",
        engineered_columns=feature_column_names,
        model_input_columns=model_use_feature_column_names,
    )
    feature_coverage_audit_frame.to_csv(feature_coverage_audit_csv_path, index=False)
    model_use_feature_coverage_summary_frame = _build_model_use_feature_coverage_summary(
        audit_frame=feature_coverage_audit_frame,
        stage_label="training",
    )
    model_use_feature_coverage_summary_frame.to_csv(
        model_use_feature_coverage_summary_csv_path,
        index=False,
    )
    model_use_feature_coverage_summary_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": "training",
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "diagnostics_only": True,
                "summary_csv_path": str(model_use_feature_coverage_summary_csv_path),
                "feature_coverage_audit_csv_path": str(feature_coverage_audit_csv_path),
                "model_use_feature_columns": list(model_use_feature_column_names),
                "feature_family_rows": model_use_feature_coverage_summary_frame.to_dict(orient="records"),
                "missing_model_use_feature_names": feature_coverage_audit_frame.loc[
                    ~feature_coverage_audit_frame["review_only_flag"].astype(bool)
                    & ~feature_coverage_audit_frame["present_in_model_use_flag"].astype(bool),
                    "feature_name",
                ].astype(str).tolist(),
                "review_only_features_in_model_use": feature_coverage_audit_frame.loc[
                    feature_coverage_audit_frame["review_only_flag"].astype(bool)
                    & feature_coverage_audit_frame["present_in_model_use_flag"].astype(bool),
                    "feature_name",
                ].astype(str).tolist(),
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )

    duplicate_key_series = pd.Series(dtype=object)
    duplicate_key_count = 0
    if "promotion_row_key" in working.columns:
        duplicate_mask = working["promotion_row_key"].astype(str).duplicated(keep=False)
        duplicate_key_series = working.loc[duplicate_mask, "promotion_row_key"].astype(str)
        duplicate_key_count = int(duplicate_key_series.nunique())

    row_count = max(int(len(export_frame.index)), 1)
    null_columns = [
        {
            "column_name": str(column_name),
            "null_count": int(export_frame[column_name].isna().sum()),
            "null_rate": round(float(export_frame[column_name].isna().sum() / row_count), 6),
        }
        for column_name in export_frame.columns
        if bool(export_frame[column_name].isna().any())
    ]
    family_rows = _training_feature_family_summary(engineered_feature_columns=feature_column_names)
    requested_family_visibility = _requested_training_family_visibility(family_rows)
    prior_manifest_comparison = _training_feature_manifest_comparison(
        current_feature_columns=feature_column_names,
        prior_feature_columns=tuple(prior_feature_columns or ()),
    )
    feature_role_audit_frame = _build_feature_role_audit_frame(
        original_frame=original_dataset_frame,
        ml_ready_frame=working,
        feature_columns=feature_column_names,
        target_columns=target_column_names,
        zero_fill_summary=export_zero_fill_summary,
    )
    feature_role_audit_frame.to_csv(feature_role_audit_csv_path, index=False)
    feature_role_audit_summary = _build_feature_role_audit_summary(
        role_audit_frame=feature_role_audit_frame,
        zero_fill_summary=upstream_zero_fill_summary or export_zero_fill_summary,
    )
    feature_role_audit_summary_json_path.write_text(
        json.dumps(feature_role_audit_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    core_head_candidate_review_frame = _build_core_head_candidate_review_frame(
        role_audit_frame=feature_role_audit_frame,
        family_rows=family_rows,
    )
    core_head_candidate_review_frame.to_csv(core_head_candidate_review_csv_path, index=False)
    core_head_candidate_review_summary = _build_core_head_candidate_review_summary(
        review_frame=core_head_candidate_review_frame,
    )
    core_head_candidate_review_summary_json_path.write_text(
        json.dumps(core_head_candidate_review_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    quality_summary = {
        "run_id": run_id,
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "row_count": int(len(working.index)),
        "column_count": int(len(working.columns)),
        "sample_row_limit": int(row_limit),
        "sample_row_count": int(min(row_limit, len(working.index))),
        "row_grain": {
            "grain_column": "promotion_row_key",
            "duplicate_key_count": duplicate_key_count,
            "duplicate_key_examples": _series_sample_values(duplicate_key_series),
        },
        "source_dataset_path": str(source_dataset_path) if source_dataset_path is not None else None,
        "source_manifest_path": str(source_manifest_path) if source_manifest_path is not None else None,
        "governed_numeric_zero_fill_summary": upstream_zero_fill_summary or export_zero_fill_summary,
        "export_numeric_zero_fill_summary": export_zero_fill_summary,
        "artifact_files": {
            "training_data_full.parquet": str(full_parquet_path),
            str(sample_csv_path.name): str(sample_csv_path),
            "training_data_sample_schema.csv": str(schema_csv_path),
            "training_data_sample_quality_summary.json": str(quality_summary_json_path),
            "training_dataset_feature_coverage_audit.csv": str(feature_coverage_audit_csv_path),
            "training_dataset_model_use_feature_coverage_summary.csv": str(model_use_feature_coverage_summary_csv_path),
            "training_dataset_model_use_feature_coverage_summary.json": str(model_use_feature_coverage_summary_json_path),
            "feature_role_audit.csv": str(feature_role_audit_csv_path),
            "feature_role_audit_summary.json": str(feature_role_audit_summary_json_path),
            "core_head_candidate_review.csv": str(core_head_candidate_review_csv_path),
            "core_head_candidate_review_summary.json": str(core_head_candidate_review_summary_json_path),
        },
        "governed_key_columns_present": key_columns,
        "columns_with_nulls": null_columns,
        "mixed_type_columns": mixed_type_columns,
        "numeric_coercion_failures": numeric_coercion_failures,
        "numeric_min_max": _numeric_min_max_summary(export_frame),
        "numeric_columns_more_than_4_decimal_places_before_rounding": precision_rows,
        "invalid_date_columns": invalid_date_columns,
        "all_null_columns": all_null_columns,
        "unexpected_all_null_columns": unexpected_all_null_columns,
        "engineered_feature_columns_present": list(feature_column_names),
        "target_columns_present": list(target_column_names),
        "review_only_engineered_feature_columns_present": sorted(
            column_name for column_name in feature_column_names if column_name in review_only_features
        ),
        "model_use_engineered_feature_columns_present": list(model_use_feature_column_names),
        "feature_coverage_audit_csv_path": str(feature_coverage_audit_csv_path),
        "feature_coverage_audit_row_count": int(len(feature_coverage_audit_frame.index)),
        "model_use_feature_coverage_summary_csv_path": str(model_use_feature_coverage_summary_csv_path),
        "model_use_feature_coverage_summary_json_path": str(model_use_feature_coverage_summary_json_path),
        "model_use_feature_coverage_summary_row_count": int(len(model_use_feature_coverage_summary_frame.index)),
        "engineered_feature_family_rows": family_rows,
        "dataset_model_use_feature_family_rows": model_use_feature_coverage_summary_frame.to_dict(orient="records"),
        "engineered_feature_families_present": sorted(
            row["feature_family"]
            for row in family_rows
            if int(row["present_feature_count"]) > 0
        ),
        "units_head_core_feature_families_present": sorted(
            row["feature_family"]
            for row in family_rows
            if row["feature_family"] in UNITS_HEAD_CORE_FEATURE_FAMILIES
            and int(row["present_feature_count"]) > 0
        ),
        "downstream_decision_support_feature_families_present": sorted(
            row["feature_family"]
            for row in family_rows
            if row["feature_family"] in DOWNSTREAM_DECISION_SUPPORT_FEATURE_FAMILIES
            and int(row["present_feature_count"]) > 0
        ),
        "engineered_feature_families_missing": sorted(
            row["feature_family"]
            for row in family_rows
            if int(row["registered_feature_count"]) > 0 and int(row["present_feature_count"]) == 0
        ),
        "model_use_feature_families_present": sorted(
            row["feature_family"]
            for row in family_rows
            if int(row["present_model_use_feature_count"]) > 0
        ),
        "model_use_feature_families_fully_present": sorted(
            row["feature_family"]
            for row in model_use_feature_coverage_summary_frame.to_dict(orient="records")
            if str(row["family_status"]) == "model_use_covered"
        ),
        "model_use_feature_families_partial": sorted(
            row["feature_family"]
            for row in model_use_feature_coverage_summary_frame.to_dict(orient="records")
            if str(row["family_status"]) in {"missing_from_model_use", "observed_partial"}
        ),
        "model_use_feature_families_missing": sorted(
            row["feature_family"]
            for row in family_rows
            if int(row["registered_feature_count"]) > 0
            and int(row["present_model_use_feature_count"]) == 0
            and int(row["present_review_only_feature_count"]) == 0
        ),
        "review_only_feature_families_present": sorted(
            row["feature_family"]
            for row in family_rows
            if int(row["present_review_only_feature_count"]) > 0
        ),
        "review_only_feature_families_excluded_by_policy": sorted(
            row["feature_family"]
            for row in model_use_feature_coverage_summary_frame.to_dict(orient="records")
            if str(row["required_presence_scope"]) == FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY
            and str(row["family_status"]) == "review_only_excluded_from_ready_dataset"
        ),
        "review_only_feature_families_missing": sorted(
            row["feature_family"]
            for row in model_use_feature_coverage_summary_frame.to_dict(orient="records")
            if str(row["required_presence_scope"]) == FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY
            and str(row["family_status"]) not in {
                "review_only_excluded_from_ready_dataset",
                "review_only_ready_no_model_leak",
            }
        ),
        "requested_family_visibility": requested_family_visibility,
        "feature_role_audit_summary_json_path": str(feature_role_audit_summary_json_path),
        "core_head_candidate_review_summary_json_path": str(core_head_candidate_review_summary_json_path),
        "prior_manifest_comparison": prior_manifest_comparison,
        "missing_identity_columns": missing_identity_columns,
        "missing_feature_columns": missing_feature_columns,
        "missing_target_columns": missing_target_columns,
        "dropped_columns": [],
    }
    quality_summary_json_path.write_text(
        json.dumps(quality_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    return PromotionTrainingDataSampleExportPaths(
        full_parquet_path=str(full_parquet_path),
        sample_csv_path=str(sample_csv_path),
        schema_csv_path=str(schema_csv_path),
        quality_summary_json_path=str(quality_summary_json_path),
        feature_coverage_audit_csv_path=str(feature_coverage_audit_csv_path),
        model_use_feature_coverage_summary_csv_path=str(model_use_feature_coverage_summary_csv_path),
        model_use_feature_coverage_summary_json_path=str(model_use_feature_coverage_summary_json_path),
        feature_role_audit_csv_path=str(feature_role_audit_csv_path),
        feature_role_audit_summary_json_path=str(feature_role_audit_summary_json_path),
        core_head_candidate_review_csv_path=str(core_head_candidate_review_csv_path),
        core_head_candidate_review_summary_json_path=str(core_head_candidate_review_summary_json_path),
    )


def _uplift_allocation_score_support_rows_present(frame: pd.DataFrame) -> bool:
    uplift_units = pd.to_numeric(
        frame.get("feature_expected_incremental_uplift_units_same_discount"),
        errors="coerce",
    ).fillna(0.0)
    total_stock_available = pd.to_numeric(
        frame.get("total_stock_available"),
        errors="coerce",
    ).fillna(0.0)
    model_use_flag = pd.to_numeric(
        frame.get("feature_probability_model_use_flag"),
        errors="coerce",
    ).fillna(0.0)
    same_discount_history_available = pd.to_numeric(
        frame.get("feature_same_discount_history_available_flag"),
        errors="coerce",
    ).fillna(0.0)
    support_rows = (
        uplift_units.gt(0.0)
        & total_stock_available.gt(0.0)
        & (model_use_flag.eq(1.0) | same_discount_history_available.eq(1.0))
    )
    return bool(support_rows.any())


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
    if any(
        token in lowered
        for token in (
            "anchor_centrality",
            "anchor_presence_support",
            "top_anchor_dependency",
            "multi_sku_promo_basket_rate",
            "three_plus_promo_sku_basket_rate",
            "basket_equilibrium",
            "conditional_sale_rate_with_anchor",
            "conditional_lift_with_anchor",
            "transaction_object_uncertainty",
        )
    ):
        return "demand_basket_equilibrium"
    if any(token in lowered for token in ("sparse_demand", "random_tail", "noise_regime")):
        return "demand_sparse_noise"
    if any(token in lowered for token in ("equilibrium", "clearing_pressure", "anchor_presence_dependency", "small_unit_option_value")):
        return "demand_micro_market_equilibrium"
    if "kalman" in lowered:
        return "demand_kalman_state_review"
    if "wasserstein" in lowered or "distribution_shape" in lowered:
        return "demand_distribution_shape_review"
    if "fragility_adjusted_opportunity" in lowered or "dag_dependency" in lowered or "dependency_support" in lowered:
        return "demand_fragility_opportunity_review"
    if column_name.startswith(ENGINEERED_FEATURE_PREFIX) and any(
        token in lowered
        for token in (
            "anchor_sku",
            "basket",
            "companion",
            "dependency",
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
        if any(token in lowered for token in ("anchor_sku", "drag_along", "dependency", "lone_random")):
            return "demand_basket_structure_dependency"
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

    # Fail loud when the governed slim units-head features are not reaching the
    # default model input. Downstream decision-support families remain in the
    # dataset and audit surfaces, but they are not required in the units head.
    # `required_engineered_features=None` means "use the production units-head
    # contract"; unit tests can pass `()` to opt out when validating tiny
    # synthetic frames.
    required_new_features = (
        iter_units_head_core_feature_columns()
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


def _registered_feature_module_by_column() -> dict[str, str]:
    module_by_feature: dict[str, str] = {}
    for definition in iter_registered_feature_modules():
        for column_name in definition.output_columns:
            module_by_feature.setdefault(str(column_name), definition.name)
    return module_by_feature


def _boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    if isinstance(value, (int, float, np.integer, np.floating)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _existing_feature_coverage_flags(audit_path: Path) -> dict[str, dict[str, bool]]:
    if not audit_path.exists():
        return {}
    existing = pd.read_csv(audit_path)
    flags: dict[str, dict[str, bool]] = {}
    for row in existing.to_dict(orient="records"):
        feature_name = str(row.get("feature_name", ""))
        if not feature_name:
            continue
        flags[feature_name] = {
            "present_in_training_ready_flag": _boolish(row.get("present_in_training_ready_flag")),
            "present_in_scoring_ready_flag": _boolish(row.get("present_in_scoring_ready_flag")),
            "present_in_model_use_flag": _boolish(row.get("present_in_model_use_flag")),
        }
    return flags


def _feature_coverage_recommendation(
    *,
    registered: bool,
    training_ready: bool,
    scoring_ready: bool,
    model_use: bool,
    review_only: bool,
) -> tuple[str, str]:
    if review_only and model_use:
        return (
            "remove_from_model_use",
            "Feature is governed review-only but appears in the final model input.",
        )
    if review_only:
        return (
            "keep_review_only",
            "Feature family is governed for diagnostics/operator review unless explicitly promoted.",
        )
    if not registered:
        return (
            "register_or_remove_unregistered_feature",
            "Feature appears outside the registry path; trace ownership before model use.",
        )
    if not training_ready and not scoring_ready:
        return (
            "investigate_missing_from_ready_datasets",
            "Registered feature was not observed in the audited training/scoring-ready dataset columns.",
        )
    if not model_use:
        return (
            "promote_to_model_use_or_document_exclusion",
            "Feature reaches a ready dataset but is excluded by model-use filtering or quality cleanup.",
        )
    return (
        "keep_model_use",
        "Registered governed feature reaches the final model input.",
    )


def _build_feature_dataset_coverage_audit(
    *,
    stage_label: str,
    engineered_columns: Sequence[str],
    model_input_columns: Sequence[str],
    existing_flags: Mapping[str, Mapping[str, bool]] | None = None,
) -> pd.DataFrame:
    """Build row-per-feature coverage across registry, ready data, and model use."""

    module_by_feature = _registered_feature_module_by_column()
    review_only_features = set(iter_review_only_engineered_feature_columns())
    engineered_feature_set = {
        str(column_name)
        for column_name in engineered_columns
        if str(column_name).startswith(ENGINEERED_FEATURE_PREFIX)
    }
    model_input_feature_set = {
        str(column_name)
        for column_name in model_input_columns
        if str(column_name).startswith(ENGINEERED_FEATURE_PREFIX)
    }
    existing_feature_names = set((existing_flags or {}).keys())
    feature_names = sorted(
        set(module_by_feature)
        | engineered_feature_set
        | model_input_feature_set
        | existing_feature_names
    )
    rows: list[dict[str, object]] = []
    for feature_name in feature_names:
        prior = (existing_flags or {}).get(feature_name, {})
        training_ready = bool(prior.get("present_in_training_ready_flag", False)) or (
            stage_label == "training" and feature_name in engineered_feature_set
        )
        scoring_ready = bool(prior.get("present_in_scoring_ready_flag", False)) or (
            stage_label == "scoring" and feature_name in engineered_feature_set
        )
        model_use = bool(prior.get("present_in_model_use_flag", False)) or feature_name in model_input_feature_set
        registered = feature_name in module_by_feature
        review_only = feature_name in review_only_features
        recommended_action, rationale = _feature_coverage_recommendation(
            registered=registered,
            training_ready=training_ready,
            scoring_ready=scoring_ready,
            model_use=model_use,
            review_only=review_only,
        )
        rows.append(
            {
                "feature_name": feature_name,
                "module_name": module_by_feature.get(feature_name, ""),
                "registry_registered_flag": registered,
                "present_in_training_ready_flag": training_ready,
                "present_in_scoring_ready_flag": scoring_ready,
                "present_in_model_use_flag": model_use,
                "review_only_flag": review_only,
                "recommended_action": recommended_action,
                "rationale": rationale,
            }
        )
    return pd.DataFrame(rows, columns=FEATURE_DATASET_COVERAGE_AUDIT_COLUMNS)


def _write_feature_dataset_coverage_audit(
    *,
    audit_path: Path,
    stage_label: str,
    engineered_columns: Sequence[str],
    model_input_columns: Sequence[str],
) -> pd.DataFrame:
    existing_flags = _existing_feature_coverage_flags(audit_path)
    audit_frame = _build_feature_dataset_coverage_audit(
        stage_label=stage_label,
        engineered_columns=engineered_columns,
        model_input_columns=model_input_columns,
        existing_flags=existing_flags,
    )
    audit_frame.to_csv(audit_path, index=False)
    return audit_frame


def _feature_family_for_coverage_row(feature_name: str, module_name: str) -> str:
    """Classify one engineered feature into the governed coverage family used in summaries."""

    lowered_feature = feature_name.lower()
    lowered_module = module_name.lower()
    if "basket_equilibrium" in lowered_module or any(
        token in lowered_feature
        for token in (
            "anchor_centrality",
            "anchor_presence_support",
            "top_anchor_dependency",
            "multi_sku_promo_basket_rate",
            "three_plus_promo_sku_basket_rate",
            "basket_equilibrium",
            "conditional_sale_rate_with_anchor",
            "conditional_lift_with_anchor",
            "transaction_object_uncertainty",
        )
    ):
        return "basket_equilibrium"
    if "basket_structure_dependency" in lowered_module:
        return "basket_structure_dependency"
    if "micro_market_equilibrium" in lowered_module or "equilibrium" in lowered_feature:
        return "micro_market_equilibrium"
    if "sparse_demand_noise" in lowered_module or "sparse_demand" in lowered_feature:
        return "sparse_demand_noise"
    if "kalman" in lowered_module or "kalman" in lowered_feature:
        return "kalman_state"
    if "distribution_shape" in lowered_module or "wasserstein" in lowered_feature:
        return "distribution_shape_distance"
    if "dag" in lowered_feature or "dependency_support" in lowered_feature:
        return "dag_dependency_support"
    if "fragility_adjusted_opportunity" in lowered_module:
        return "fragility_opportunity"
    if "pca" in lowered_feature or "pca" in lowered_module:
        return "pca"
    if "situational_awareness" in lowered_module or "situational" in lowered_feature:
        return "situational_awareness"
    if "probability" in lowered_feature or "probability" in lowered_module:
        return "probability"
    if "target_stock" in lowered_module or "end_of_promo_target" in lowered_feature:
        return "target_stock_shape"
    if "allocation" in lowered_module or any(
        token in lowered_feature
        for token in ("allocation", "trust_floor", "capital_tied", "overallocation")
    ):
        return "allocation_discipline"
    if any(
        token in lowered_feature
        for token in ("same_discount", "same_or_better", "prior_promo", "promo_history", "historical_")
    ):
        return "same_discount_promo_history"
    if any(
        token in lowered_feature or token in lowered_module
        for token in ("fragility", "opportunity", "survival", "shape", "growth_curve")
    ):
        return "fragility_opportunity_shape"
    if "basket" in lowered_feature or "basket" in lowered_module:
        return "basket_context"
    if any(token in lowered_module for token in ("discount", "uplift", "baseline")):
        return "baseline_discount_uplift"
    return "other_engineered_feature"


def _build_model_use_feature_coverage_summary(
    *,
    audit_frame: pd.DataFrame,
    stage_label: str,
) -> pd.DataFrame:
    """Aggregate feature coverage into governed model-use and review-only families."""

    working = audit_frame.copy()
    working["feature_family"] = [
        _feature_family_for_coverage_row(str(row.feature_name), str(row.module_name))
        for row in working.itertuples(index=False)
    ]
    requirements = {
        row["feature_family"]: row
        for row in MODEL_USE_FEATURE_FAMILY_REQUIREMENTS
    }
    family_names = list(requirements)
    family_names.extend(
        family_name
        for family_name in sorted(set(working["feature_family"].astype(str)))
        if family_name not in requirements
    )
    rows: list[dict[str, object]] = []
    for family_name in family_names:
        family_frame = working.loc[working["feature_family"].astype(str).eq(family_name)]
        requirement = requirements.get(
            family_name,
            {
                "required_presence_scope": FEATURE_FAMILY_SCOPE_IF_PRESENT,
                "rationale": "Additional engineered feature family observed during audit.",
            },
        )
        feature_count = int(len(family_frame.index))
        training_ready_count = int(family_frame["present_in_training_ready_flag"].astype(bool).sum()) if feature_count else 0
        scoring_ready_count = int(family_frame["present_in_scoring_ready_flag"].astype(bool).sum()) if feature_count else 0
        model_use_count = int(family_frame["present_in_model_use_flag"].astype(bool).sum()) if feature_count else 0
        review_only_count = int(family_frame["review_only_flag"].astype(bool).sum()) if feature_count else 0
        missing_model_use_count = int(
            (
                ~family_frame["review_only_flag"].astype(bool)
                & ~family_frame["present_in_model_use_flag"].astype(bool)
            ).sum()
        ) if feature_count else 0
        review_only_model_use_leak_count = int(
            (
                family_frame["review_only_flag"].astype(bool)
                & family_frame["present_in_model_use_flag"].astype(bool)
            ).sum()
        ) if feature_count else 0
        family_status = _coverage_family_status(
            required_presence_scope=str(requirement["required_presence_scope"]),
            stage_label=stage_label,
            feature_count=feature_count,
            training_ready_count=training_ready_count,
            scoring_ready_count=scoring_ready_count,
            present_model_use_count=model_use_count,
            missing_model_use_count=missing_model_use_count,
            review_only_feature_count=review_only_count,
            review_only_model_use_leak_count=review_only_model_use_leak_count,
        )
        rows.append(
            {
                "feature_family": family_name,
                "required_presence_scope": requirement["required_presence_scope"],
                "feature_count": feature_count,
                "present_in_training_ready_count": training_ready_count,
                "present_in_scoring_ready_count": scoring_ready_count,
                "present_in_model_use_count": model_use_count,
                "review_only_feature_count": review_only_count,
                "missing_model_use_feature_count": missing_model_use_count,
                "review_only_model_use_leak_count": review_only_model_use_leak_count,
                "family_status": family_status,
                "rationale": requirement["rationale"],
            }
        )
    return pd.DataFrame(rows, columns=MODEL_USE_FEATURE_COVERAGE_SUMMARY_COLUMNS)


def _coverage_family_status(
    *,
    required_presence_scope: str,
    stage_label: str,
    feature_count: int,
    training_ready_count: int,
    scoring_ready_count: int,
    present_model_use_count: int,
    missing_model_use_count: int,
    review_only_feature_count: int,
    review_only_model_use_leak_count: int,
) -> str:
    """Return the governed status label for one feature-family coverage row."""

    if review_only_model_use_leak_count > 0:
        return "review_only_leaked_to_model_use"
    if feature_count == 0:
        return "not_observed"
    ready_count = training_ready_count if stage_label == "training" else scoring_ready_count
    if required_presence_scope == FEATURE_FAMILY_SCOPE_MODEL_USE:
        if ready_count == 0:
            return "missing_from_ready_dataset"
        if missing_model_use_count > 0:
            return "missing_from_model_use"
        return "model_use_covered"
    if required_presence_scope == FEATURE_FAMILY_SCOPE_REVIEW_ONLY_READY:
        if ready_count == 0:
            return "review_only_excluded_from_ready_dataset"
        return "review_only_ready_no_model_leak"
    if ready_count == 0:
        if review_only_feature_count == feature_count and present_model_use_count == 0:
            return "review_only_excluded_from_ready_dataset"
        return "not_observed"
    if missing_model_use_count > 0:
        return "observed_partial"
    if present_model_use_count > 0:
        return "model_use_covered"
    if review_only_feature_count > 0:
        return "review_only_excluded_from_ready_dataset"
    return "observed"


def _write_model_use_feature_coverage_summary(
    *,
    summary_csv_path: Path,
    summary_json_path: Path,
    run_id: str,
    stage_label: str,
    audit_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Write compact CSV and JSON coverage summaries for governed feature families."""

    summary_frame = _build_model_use_feature_coverage_summary(
        audit_frame=audit_frame,
        stage_label=stage_label,
    )
    summary_frame.to_csv(summary_csv_path, index=False)
    missing_model_use = audit_frame.loc[
        ~audit_frame["review_only_flag"].astype(bool)
        & ~audit_frame["present_in_model_use_flag"].astype(bool),
        "feature_name",
    ].astype(str).tolist()
    review_only_leaks = audit_frame.loc[
        audit_frame["review_only_flag"].astype(bool)
        & audit_frame["present_in_model_use_flag"].astype(bool),
        "feature_name",
    ].astype(str).tolist()
    summary_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": stage_label,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "diagnostics_only": True,
                "summary_csv_path": str(summary_csv_path),
                "feature_family_rows": summary_frame.to_dict(orient="records"),
                "missing_model_use_feature_names": missing_model_use,
                "review_only_features_in_model_use": review_only_leaks,
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    return summary_frame


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
    feature_dataset_coverage_audit_csv_path = inspection_root / "feature_dataset_coverage_audit.csv"
    model_use_feature_coverage_summary_csv_path = inspection_root / f"model_use_feature_coverage_summary_{stage_label}.csv"
    model_use_feature_coverage_summary_json_path = inspection_root / f"model_use_feature_coverage_summary_{stage_label}.json"
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
            for column_name in iter_units_head_core_feature_columns()
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
    feature_dataset_coverage_audit_frame = _write_feature_dataset_coverage_audit(
        audit_path=feature_dataset_coverage_audit_csv_path,
        stage_label=stage_label,
        engineered_columns=engineered_columns,
        model_input_columns=tuple(model_input.columns),
    )
    model_use_feature_coverage_summary_frame = _write_model_use_feature_coverage_summary(
        summary_csv_path=model_use_feature_coverage_summary_csv_path,
        summary_json_path=model_use_feature_coverage_summary_json_path,
        run_id=run_id,
        stage_label=stage_label,
        audit_frame=feature_dataset_coverage_audit_frame,
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
                "feature_dataset_coverage_audit_csv_path": str(feature_dataset_coverage_audit_csv_path),
                "feature_dataset_coverage_audit_row_count": int(len(feature_dataset_coverage_audit_frame.index)),
                "model_use_feature_coverage_summary_csv_path": str(model_use_feature_coverage_summary_csv_path),
                "model_use_feature_coverage_summary_json_path": str(model_use_feature_coverage_summary_json_path),
                "model_use_feature_coverage_summary_row_count": int(len(model_use_feature_coverage_summary_frame.index)),
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
        feature_dataset_coverage_audit_csv_path=str(feature_dataset_coverage_audit_csv_path),
        model_use_feature_coverage_summary_csv_path=str(model_use_feature_coverage_summary_csv_path),
        model_use_feature_coverage_summary_json_path=str(model_use_feature_coverage_summary_json_path),
        contract_validation_json_path=str(contract_validation_json_path),
        feature_quality_audit_csv_path=quality_artifact_paths.get("feature_quality_audit_csv_path"),
        feature_quality_audit_json_path=quality_artifact_paths.get("feature_quality_audit_json_path"),
        feature_leakage_review_csv_path=quality_artifact_paths.get("feature_leakage_review_csv_path"),
        feature_correlation_review_csv_path=quality_artifact_paths.get("feature_correlation_review_csv_path"),
        model_input_quality_summary_csv_path=quality_artifact_paths.get("model_input_quality_summary_csv_path"),
        model_input_quality_summary_json_path=quality_artifact_paths.get("model_input_quality_summary_json_path"),
        model_input_quality_summary_txt_path=quality_artifact_paths.get("model_input_quality_summary_txt_path"),
    )
