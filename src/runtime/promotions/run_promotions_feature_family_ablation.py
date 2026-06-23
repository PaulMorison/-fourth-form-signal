from __future__ import annotations

"""Diagnostics-only family ablation for governed promotions training datasets."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from threading import Event, Thread
from time import perf_counter
from typing import Sequence

import numpy as np
import pandas as pd

from models.promotions.allocation_calibration import compute_allocation_aware_cap_units
from models.promotions.order_policy_adjustments import build_order_policy_adjustments
from models.promotions.promotion_demand_backtest import (
    compute_backtest_rows,
    compute_backtest_summary,
)
from models.promotions.promotion_execution_scorecard import (
    build_promotion_execution_scorecard_rows,
    build_promotion_execution_scorecard_summary,
)
from models.promotions.preprocessing import prepare_model_input_frame
from models.promotions.model_input_quality import UNITS_HEAD_CORE_FEATURE_FAMILIES
from models.promotions.trainer import PromotionModelTrainer
from runtime.promotions.config import PromotionArtifactPaths
from state.promotions.datasets.model_input_export import (
    _feature_family_for_coverage_row,
    _registered_feature_module_by_column,
)
from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (
    build_live_order_decision_diagnostics,
)


BASE_CORE_REQUIRED_FAMILIES: tuple[str, ...] = tuple(UNITS_HEAD_CORE_FEATURE_FAMILIES)

MICRO_INTERACTION_SOURCE_FAMILIES: tuple[str, ...] = (
    "basket_structure_dependency",
    "micro_market_equilibrium",
)

MICRO_INTERACTION_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_micro_interaction_anchor_market_pressure",
    "feature_micro_interaction_dependency_presence",
    "feature_micro_interaction_drag_support",
    "feature_micro_interaction_convexity_support",
)

SCENARIO_BASE_CORE_ONLY = "base_core_only"
SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION = "base_core_plus_micro_interaction"
SCENARIO_BASE_CORE_PLUS_TARGET_STOCK = "base_core_plus_target_stock_shape"
SCENARIO_BASE_CORE_PLUS_ALLOCATION = "base_core_plus_allocation_discipline"
SCENARIO_BASE_CORE_PLUS_MICRO_MARKET = "base_core_plus_micro_market_equilibrium"

PROMO_SAFE_PCT_ERROR_IMPROVEMENT_THRESHOLD = -0.10
STORE_IMPROVEMENT_SHARE_THRESHOLD = 0.60
TRUST_MISS_TOLERANCE_DELTA = 0.0

PROMO_TYPE_BUCKET_NORMAL = "normal catalogue"
PROMO_TYPE_BUCKET_SALES_EVENT = "sales event"
PROMO_TYPE_BUCKET_ONLINE = "online"
PROMO_TYPE_BUCKET_NEW_LINE = "new line"
PROMO_TYPE_BUCKET_OTHER = "other"


@dataclass(frozen=True)
class FeatureFamilyAblationScenario:
    scenario_id: str
    scenario_kind: str
    description: str
    feature_columns: tuple[str, ...]
    included_families: tuple[str, ...]
    excluded_families: tuple[str, ...]


@dataclass(frozen=True)
class FeatureFamilyAblationArtifacts:
    output_root: str
    summary_csv_path: str
    summary_json_path: str
    promo_type_breakdown_csv_path: str
    store_level_robustness_csv_path: str
    sparse_demand_breakdown_csv_path: str
    trust_capital_breakdown_csv_path: str
    conclusion_json_path: str
    runtime_manifest_json_path: str


class PromotionFeatureFamilyAblationError(ValueError):
    """Raised when the governed family ablation contract cannot be satisfied."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


def _scenario_heartbeat_handle(scenario_id: str, *, heartbeat_seconds: float = 20.0) -> tuple[Event, Thread]:
    stop_event = Event()

    def _emit() -> None:
        while not stop_event.wait(heartbeat_seconds):
            print(
                f"feature_family_ablation_scenario_heartbeat: {scenario_id}",
                file=sys.stderr,
                flush=True,
            )

    thread = Thread(target=_emit, daemon=True)
    return stop_event, thread


def build_parser() -> object:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run governed feature-family ablations for a promotions training dataset."
    )
    parser.add_argument("--run-id", required=True, help="Training dataset run id to evaluate.")
    parser.add_argument("--artifact-root", help="Override governed promotions artifact root.")
    parser.add_argument("--output-root", help="Override ablation output root. Defaults to inspection/<run-id>/feature_family_ablation.")
    return parser


def _required_file(path: Path, *, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def _load_dataset_and_manifest(
    *,
    run_id: str,
    artifact_paths: PromotionArtifactPaths,
) -> tuple[pd.DataFrame, Path, dict[str, object], Path]:
    dataset_path = _required_file(
        artifact_paths.training_dataset_path(run_id),
        label="training dataset parquet",
    )
    manifest_path = _required_file(
        artifact_paths.dataset_manifest_path(run_id),
        label="dataset manifest",
    )
    dataset = pd.read_parquet(dataset_path)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return dataset, dataset_path, manifest_payload, manifest_path


def _feature_family_column_map(feature_columns: Sequence[str]) -> dict[str, tuple[str, ...]]:
    module_by_feature = _registered_feature_module_by_column()
    families: dict[str, list[str]] = {}
    for column_name in feature_columns:
        family_name = _feature_family_for_coverage_row(
            str(column_name),
            module_by_feature.get(str(column_name), ""),
        )
        families.setdefault(family_name, []).append(str(column_name))
    return {family_name: tuple(columns) for family_name, columns in families.items()}


def build_feature_family_ablation_scenarios(feature_columns: Sequence[str]) -> tuple[FeatureFamilyAblationScenario, ...]:
    family_map = _feature_family_column_map(feature_columns)
    missing_base_core_families = [
        family_name for family_name in BASE_CORE_REQUIRED_FAMILIES if family_name not in family_map
    ]
    if missing_base_core_families:
        raise PromotionFeatureFamilyAblationError(
            "Training dataset is missing required units-head core feature families.",
            details={
                "feature_columns": list(feature_columns),
                "missing_base_core_families": missing_base_core_families,
            },
        )
    required_addback_families = (
        "target_stock_shape",
        "allocation_discipline",
        "micro_market_equilibrium",
    )
    missing_addback_families = [
        family_name for family_name in required_addback_families if family_name not in family_map
    ]
    if missing_addback_families:
        raise PromotionFeatureFamilyAblationError(
            "Training dataset is missing required downstream add-back feature families.",
            details={
                "feature_columns": list(feature_columns),
                "missing_addback_families": missing_addback_families,
            },
        )
    missing_interaction_source_families = [
        family_name
        for family_name in MICRO_INTERACTION_SOURCE_FAMILIES
        if family_name not in family_map
    ]
    if missing_interaction_source_families:
        raise PromotionFeatureFamilyAblationError(
            "Training dataset is missing required basket×micro interaction source families.",
            details={
                "feature_columns": list(feature_columns),
                "missing_interaction_source_families": missing_interaction_source_families,
            },
        )

    all_feature_columns = tuple(dict.fromkeys(str(column_name) for column_name in feature_columns))
    base_core_feature_columns = tuple(
        dict.fromkeys(
            column_name
            for family_name in BASE_CORE_REQUIRED_FAMILIES
            for column_name in family_map[family_name]
        )
    )

    def _scenario_columns(*families: str) -> tuple[str, ...]:
        selected = [*base_core_feature_columns]
        for family_name in families:
            selected.extend(family_map.get(family_name, ()))
        return tuple(dict.fromkeys(selected))

    def _excluded_families(*included_families: str) -> tuple[str, ...]:
        included = set(included_families)
        return tuple(sorted(family for family in family_map if family not in included))

    scenarios: list[FeatureFamilyAblationScenario] = [
        FeatureFamilyAblationScenario(
            scenario_id="control_full_model_visible",
            scenario_kind="control_full",
            description="Full governed model-visible feature set.",
            feature_columns=all_feature_columns,
            included_families=tuple(sorted(family_map)),
            excluded_families=(),
        ),
        FeatureFamilyAblationScenario(
            scenario_id=SCENARIO_BASE_CORE_ONLY,
            scenario_kind="base_core_only",
            description=(
                "Slim base core: basket_structure_dependency, sparse_demand_noise, "
                "probability, and same_discount_promo_history only."
            ),
            feature_columns=base_core_feature_columns,
            included_families=BASE_CORE_REQUIRED_FAMILIES,
            excluded_families=_excluded_families(*BASE_CORE_REQUIRED_FAMILIES),
        ),
        FeatureFamilyAblationScenario(
            scenario_id=SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION,
            scenario_kind="base_core_plus_interaction_bundle",
            description=(
                "Base core plus basket_structure_dependency×micro_market_equilibrium "
                "interaction bundle only."
            ),
            feature_columns=tuple(dict.fromkeys((*base_core_feature_columns, *MICRO_INTERACTION_FEATURE_COLUMNS))),
            included_families=(*BASE_CORE_REQUIRED_FAMILIES, "micro_interaction"),
            excluded_families=_excluded_families(*BASE_CORE_REQUIRED_FAMILIES),
        ),
        FeatureFamilyAblationScenario(
            scenario_id=SCENARIO_BASE_CORE_PLUS_TARGET_STOCK,
            scenario_kind="base_core_plus_single_family",
            description="Base core plus target_stock_shape only.",
            feature_columns=_scenario_columns("target_stock_shape"),
            included_families=(*BASE_CORE_REQUIRED_FAMILIES, "target_stock_shape"),
            excluded_families=_excluded_families(*BASE_CORE_REQUIRED_FAMILIES, "target_stock_shape"),
        ),
        FeatureFamilyAblationScenario(
            scenario_id=SCENARIO_BASE_CORE_PLUS_ALLOCATION,
            scenario_kind="base_core_plus_single_family",
            description="Base core plus allocation_discipline only.",
            feature_columns=_scenario_columns("allocation_discipline"),
            included_families=(*BASE_CORE_REQUIRED_FAMILIES, "allocation_discipline"),
            excluded_families=_excluded_families(*BASE_CORE_REQUIRED_FAMILIES, "allocation_discipline"),
        ),
        FeatureFamilyAblationScenario(
            scenario_id=SCENARIO_BASE_CORE_PLUS_MICRO_MARKET,
            scenario_kind="base_core_plus_single_family",
            description="Base core plus full micro_market_equilibrium family.",
            feature_columns=_scenario_columns("micro_market_equilibrium"),
            included_families=(*BASE_CORE_REQUIRED_FAMILIES, "micro_market_equilibrium"),
            excluded_families=_excluded_families(*BASE_CORE_REQUIRED_FAMILIES, "micro_market_equilibrium"),
        ),
    ]
    return tuple(scenarios)


def _base_dataset_columns(dataset: pd.DataFrame) -> tuple[str, ...]:
    return tuple(column_name for column_name in dataset.columns if not str(column_name).startswith("feature_"))


def _scenario_dataset(dataset: pd.DataFrame, scenario: FeatureFamilyAblationScenario) -> pd.DataFrame:
    working = dataset.copy()
    if scenario.scenario_id != SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION:
        return working
    interaction_bundle = _build_micro_interaction_bundle(working)
    for column_name in interaction_bundle.columns:
        working[column_name] = interaction_bundle[column_name]
    return working


def _numeric_feature(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0).astype("float64")


def _build_micro_interaction_bundle(dataset: pd.DataFrame) -> pd.DataFrame:
    anchor_score = _numeric_feature(dataset, "feature_basket_anchor_sku_score").clip(0.0, 1.0)
    dependency_score = _numeric_feature(dataset, "feature_basket_conditional_dependency_score").clip(0.0, 1.0)
    drag_score = _numeric_feature(dataset, "feature_basket_drag_along_dependency_score").clip(0.0, 1.0)
    convexity_support = _numeric_feature(dataset, "feature_basket_convexity_support_score").clip(0.0, 1.0)
    market_clearing = _numeric_feature(dataset, "feature_micro_market_clearing_pressure").clip(0.0, 1.0)
    anchor_presence = _numeric_feature(dataset, "feature_anchor_presence_dependency_score").clip(0.0, 1.0)
    conditional_sale = _numeric_feature(dataset, "feature_conditional_sale_probability_given_anchor").clip(0.0, 1.0)
    convexity_to_capital = _numeric_feature(dataset, "feature_convexity_to_capital_score").clip(0.0, 1.0)

    return pd.DataFrame(
        {
            "feature_micro_interaction_anchor_market_pressure": (anchor_score * market_clearing).clip(0.0, 1.0),
            "feature_micro_interaction_dependency_presence": (dependency_score * anchor_presence).clip(0.0, 1.0),
            "feature_micro_interaction_drag_support": (drag_score * conditional_sale).clip(0.0, 1.0),
            "feature_micro_interaction_convexity_support": (convexity_support * convexity_to_capital).clip(0.0, 1.0),
        },
        index=dataset.index,
    )


def _normalize_promo_type_bucket(promo_type: object, promotion_name: object) -> str:
    combined = f"{promo_type or ''} {promotion_name or ''}".strip().lower()
    if "new line" in combined or "newline" in combined or "newline" in combined.replace(" ", "") or "launch" in combined:
        return PROMO_TYPE_BUCKET_NEW_LINE
    if "online" in combined:
        return PROMO_TYPE_BUCKET_ONLINE
    if "sales" in combined or "event" in combined:
        return PROMO_TYPE_BUCKET_SALES_EVENT
    if "catalogue" in combined or combined:
        return PROMO_TYPE_BUCKET_NORMAL
    return PROMO_TYPE_BUCKET_OTHER


def _test_source_context(full_dataset: pd.DataFrame, test_mask: pd.Series) -> pd.DataFrame:
    source = full_dataset.loc[test_mask].copy().reset_index(drop=True)
    context = pd.DataFrame({"promotion_row_key": source["promotion_row_key"].astype(str)})
    context["promo_type_bucket"] = [
        _normalize_promo_type_bucket(row.get("promo_type"), row.get("promotion_name"))
        for row in source.to_dict(orient="records")
    ]
    basket_anchor_score = pd.to_numeric(source.get("feature_basket_anchor_sku_score"), errors="coerce").fillna(0.0)
    basket_evidence = pd.to_numeric(source.get("feature_basket_structure_evidence_available_flag"), errors="coerce").fillna(0.0)
    context["basket_led_segment_flag"] = ((basket_evidence.ge(1.0)) | (basket_anchor_score.ge(0.55))).astype(int)
    sparse_stable = pd.to_numeric(source.get("feature_sparse_demand_stable_low_trust_flag"), errors="coerce").fillna(0.0)
    intermittent = pd.to_numeric(source.get("feature_intermittent_demand_flag"), errors="coerce").fillna(0.0)
    context["sparse_segment_flag"] = ((sparse_stable.ge(1.0)) | (intermittent.ge(1.0))).astype(int)
    high_demand = pd.to_numeric(source.get("feature_high_base_demand_end_cover_flag"), errors="coerce").fillna(0.0)
    context["high_demand_anchor_segment_flag"] = high_demand.ge(1.0).astype(int)
    trust_gap = pd.to_numeric(source.get("feature_units_needed_for_trust_floor"), errors="coerce").fillna(0.0)
    high_demand_gap = pd.to_numeric(source.get("feature_units_needed_for_high_demand_cover"), errors="coerce").fillna(0.0)
    no_history = pd.to_numeric(source.get("feature_no_promo_history_flag"), errors="coerce").fillna(0.0)
    context["trust_floor_segment_flag"] = ((trust_gap.gt(0.0)) | (high_demand_gap.gt(0.0)) | (no_history.ge(1.0))).astype(int)
    capital_drag = pd.to_numeric(source.get("feature_excess_month_end_capital_drag"), errors="coerce").fillna(0.0)
    capital_above_target = pd.to_numeric(source.get("feature_capital_tied_above_trust_target"), errors="coerce").fillna(0.0)
    cash_efficiency = pd.to_numeric(source.get("feature_cashflow_efficiency_score"), errors="coerce").fillna(1.0)
    context["capital_efficiency_segment_flag"] = ((capital_drag.gt(0.0)) | (capital_above_target.gt(0.0)) | cash_efficiency.lt(0.95)).astype(int)
    return context.drop_duplicates("promotion_row_key")


def _build_test_predictions_frame(
    *,
    dataset: pd.DataFrame,
    model_input: pd.DataFrame,
    test_mask: pd.Series,
    units_model,
) -> pd.DataFrame:
    if int(test_mask.sum()) == 0:
        return pd.DataFrame()
    test_features = model_input.loc[test_mask]
    raw_predicted_units = pd.Series(
        units_model.predict(test_features),
        index=test_features.index,
        dtype="float64",
    ).clip(lower=0.0)
    test_dataset = dataset.loc[test_mask]
    allocation_cap_units = compute_allocation_aware_cap_units(
        test_dataset,
        raw_predicted_units,
    )
    calibrated_predicted_units = raw_predicted_units.clip(lower=0.0)
    diagnostics = build_live_order_decision_diagnostics(
        test_dataset,
        raw_predicted_units=raw_predicted_units,
        predicted_units=calibrated_predicted_units,
    )
    policy_adjustments = build_order_policy_adjustments(
        test_dataset,
        raw_predicted_units=raw_predicted_units,
        calibrated_predicted_units=calibrated_predicted_units,
        diagnostics_frame=diagnostics,
    )
    policy_adjusted_predicted_units = pd.to_numeric(
        policy_adjustments["adjusted_order_cap_units"],
        errors="coerce",
    ).fillna(calibrated_predicted_units).clip(lower=0.0)
    passthrough = [
        column_name
        for column_name in PromotionModelTrainer._BACKTEST_PASSTHROUGH_COLUMNS
        if column_name in test_dataset.columns
    ]
    out = test_dataset.loc[:, passthrough].copy()
    out["raw_predicted_units_total_promo"] = raw_predicted_units.values
    out["calibrated_predicted_units_total_promo"] = calibrated_predicted_units.values
    out["allocation_cap_units"] = allocation_cap_units.values
    out["policy_adjusted_predicted_units_total_promo"] = policy_adjusted_predicted_units.values
    out["policy_adjustment_reason"] = policy_adjustments["policy_adjustment_reason"].values
    # Phase 2/3: demand export follows calibrated (raw) path, not policy cap.
    out["predicted_units_total_promo"] = calibrated_predicted_units.values
    if "actual_units_sold_promo" not in out.columns and "actual_units_sold" in out.columns:
        out["actual_units_sold_promo"] = out["actual_units_sold"]
    return out.reset_index(drop=True)


def _evaluation_rows(
    *,
    predictions: pd.DataFrame,
    source_frame: pd.DataFrame,
    source_context: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
    backtest_rows = compute_backtest_rows(predictions)
    backtest_summary = compute_backtest_summary(backtest_rows)
    scorecard_rows = build_promotion_execution_scorecard_rows(
        backtest_rows=backtest_rows,
        source_frame=source_frame,
    )
    scorecard_summary = build_promotion_execution_scorecard_summary(scorecard_rows=scorecard_rows)
    evaluation_rows = backtest_rows.merge(
        scorecard_rows.loc[
            :,
            [
                "promotion_row_key",
                "trust_floor_shape_policy_class",
                "below_trust_floor_missed_opportunity_flag",
                "capital_drag_dollars",
                "effective_sharpe_like_gp_per_drag",
            ],
        ],
        on="promotion_row_key",
        how="left",
        validate="one_to_one",
    ).merge(
        source_context,
        on="promotion_row_key",
        how="left",
        validate="one_to_one",
    )
    return evaluation_rows, backtest_summary, scorecard_summary


def _metric_summary_rows(rows: pd.DataFrame) -> dict[str, float | int]:
    if rows.empty:
        return {
            "row_count": 0,
            "mae_units": 0.0,
            "rmse_units": 0.0,
            "promo_safe_pct_error": 0.0,
            "directional_bias_units": 0.0,
            "stockout_miss_rate": 0.0,
            "trust_floor_miss_rate": 0.0,
            "over_allocation_capital_drag_dollars_mean": 0.0,
            "end_shape_success_rate": 0.0,
            "effective_sharpe_like_gp_per_drag_mean": 0.0,
        }
    predicted = pd.to_numeric(rows["predicted_units_total_promo"], errors="coerce").fillna(0.0)
    actual = pd.to_numeric(rows["actual_units_sold_promo"], errors="coerce").fillna(0.0)
    error = predicted - actual
    squared_error = error.pow(2)
    return {
        "row_count": int(len(rows.index)),
        "mae_units": round(float(error.abs().mean()), 4),
        "rmse_units": round(float(np.sqrt(squared_error.mean())), 4),
        "promo_safe_pct_error": round(float(pd.to_numeric(rows["absolute_pct_error"], errors="coerce").fillna(0.0).mean()), 4),
        "directional_bias_units": round(float(error.mean()), 4),
        "stockout_miss_rate": round(float(pd.to_numeric(rows["zero_oos_flag"], errors="coerce").fillna(0.0).mean()), 4),
        "trust_floor_miss_rate": round(float(pd.to_numeric(rows["below_trust_floor_missed_opportunity_flag"], errors="coerce").fillna(0.0).mean()), 4),
        "over_allocation_capital_drag_dollars_mean": round(float(pd.to_numeric(rows["capital_drag_dollars"], errors="coerce").fillna(0.0).mean()), 4),
        "end_shape_success_rate": round(float(pd.to_numeric(rows["end_shape_success_flag"], errors="coerce").fillna(0.0).mean()), 4),
        "effective_sharpe_like_gp_per_drag_mean": round(float(pd.to_numeric(rows["effective_sharpe_like_gp_per_drag"], errors="coerce").fillna(0.0).mean()), 4),
    }


def _scenario_summary_row(
    *,
    scenario: FeatureFamilyAblationScenario,
    feature_count: int,
    model_input_feature_count: int,
    backtest_summary: dict[str, object],
    scorecard_summary: dict[str, object],
    evaluation_rows: pd.DataFrame,
    runtime_seconds: float,
) -> dict[str, object]:
    metric_summary = _metric_summary_rows(evaluation_rows)
    return {
        "scenario_id": scenario.scenario_id,
        "scenario_kind": scenario.scenario_kind,
        "description": scenario.description,
        "included_families": "|".join(scenario.included_families),
        "excluded_families": "|".join(scenario.excluded_families),
        "dataset_feature_column_count": int(feature_count),
        "model_input_feature_count": int(model_input_feature_count),
        "row_count": int(metric_summary["row_count"]),
        "mae_units": float(metric_summary["mae_units"]),
        "rmse_units": float(metric_summary["rmse_units"]),
        "promo_safe_pct_error": float(metric_summary["promo_safe_pct_error"]),
        "directional_bias_units": float(metric_summary["directional_bias_units"]),
        "stockout_miss_rate": float(metric_summary["stockout_miss_rate"]),
        "trust_floor_miss_rate": float(metric_summary["trust_floor_miss_rate"]),
        "over_allocation_capital_drag_dollars_mean": float(metric_summary["over_allocation_capital_drag_dollars_mean"]),
        "end_shape_success_rate": float(metric_summary["end_shape_success_rate"]),
        "effective_sharpe_like_gp_per_drag_mean": float(metric_summary["effective_sharpe_like_gp_per_drag_mean"]),
        "within_20pct_rate": float(backtest_summary["within_20pct_rate"]),
        "high_demand_14d_success_rate": float(scorecard_summary["high_demand_14d_success_rate"]),
        "runtime_seconds": round(float(runtime_seconds), 4),
    }


def _promo_type_breakdown_rows(*, scenario_id: str, evaluation_rows: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for promo_type_bucket, group in evaluation_rows.groupby("promo_type_bucket", dropna=False):
        metrics = _metric_summary_rows(group)
        rows.append({"scenario_id": scenario_id, "promo_type_bucket": str(promo_type_bucket), **metrics})
    return rows


def _store_level_rows(*, scenario_id: str, evaluation_rows: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for store_number, group in evaluation_rows.groupby("store_number", dropna=False):
        metrics = _metric_summary_rows(group)
        rows.append({"scenario_id": scenario_id, "store_number": str(store_number), **metrics})
    return rows


def _segment_summary_rows(evaluation_rows: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    segment_rows = {
        "sparse": evaluation_rows.loc[evaluation_rows["sparse_segment_flag"].fillna(0).astype(int).ge(1)],
        "dense": evaluation_rows.loc[evaluation_rows["sparse_segment_flag"].fillna(0).astype(int).lt(1)],
        "basket_led": evaluation_rows.loc[evaluation_rows["basket_led_segment_flag"].fillna(0).astype(int).ge(1)],
        "high_demand_anchor": evaluation_rows.loc[evaluation_rows["high_demand_anchor_segment_flag"].fillna(0).astype(int).ge(1)],
        "trust_floor": evaluation_rows.loc[evaluation_rows["trust_floor_segment_flag"].fillna(0).astype(int).ge(1)],
        "capital_efficiency": evaluation_rows.loc[evaluation_rows["capital_efficiency_segment_flag"].fillna(0).astype(int).ge(1)],
    }
    return {segment_name: _metric_summary_rows(frame) for segment_name, frame in segment_rows.items()}


def _segment_breakdown_rows(
    *,
    scenario_id: str,
    segment_metrics: dict[str, dict[str, float | int]],
    segment_names: tuple[str, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for segment_name in segment_names:
        metrics = segment_metrics.get(segment_name, _metric_summary_rows(pd.DataFrame()))
        rows.append({"scenario_id": scenario_id, "segment_name": segment_name, **metrics})
    return rows


def _with_deltas(summary_rows: pd.DataFrame, *, control_id: str, base_id: str) -> pd.DataFrame:
    working = summary_rows.copy()
    control_row = working.loc[working["scenario_id"].eq(control_id)].iloc[0]
    base_row = working.loc[working["scenario_id"].eq(base_id)].iloc[0]
    delta_columns = (
        "mae_units",
        "rmse_units",
        "promo_safe_pct_error",
        "directional_bias_units",
        "stockout_miss_rate",
        "trust_floor_miss_rate",
        "over_allocation_capital_drag_dollars_mean",
        "end_shape_success_rate",
        "effective_sharpe_like_gp_per_drag_mean",
    )
    for column_name in delta_columns:
        working[f"delta_vs_control_{column_name}"] = working[column_name].astype(float) - float(control_row[column_name])
        working[f"delta_vs_base_{column_name}"] = working[column_name].astype(float) - float(base_row[column_name])
    return working


def _ranked_conclusion(
    *,
    summary_rows: pd.DataFrame,
    segment_metrics: dict[str, dict[str, dict[str, float | int]]],
    store_frame: pd.DataFrame,
) -> dict[str, object]:
    scenario_frame = summary_rows.set_index("scenario_id")
    required_scenarios = {
        SCENARIO_BASE_CORE_ONLY,
        SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION,
        SCENARIO_BASE_CORE_PLUS_TARGET_STOCK,
        SCENARIO_BASE_CORE_PLUS_ALLOCATION,
        SCENARIO_BASE_CORE_PLUS_MICRO_MARKET,
    }
    missing_scenarios = sorted(required_scenarios.difference(scenario_frame.index.astype(str)))
    if missing_scenarios:
        return {
            "recommendation": "insufficient_scenarios",
            "missing_required_scenarios": missing_scenarios,
            "interaction_bundle": None,
            "full_micro_family": None,
            "downstream_addbacks": None,
            "store_robustness": None,
            "reference_scenarios": None,
            "candidate_columns_for_later_promotion": [],
            "promotion_risks": [],
            "acceptance_thresholds": {
                "promo_safe_pct_error_improvement_vs_base_max": PROMO_SAFE_PCT_ERROR_IMPROVEMENT_THRESHOLD,
                "store_improvement_share_min": STORE_IMPROVEMENT_SHARE_THRESHOLD,
                "trust_floor_miss_rate_delta_max": TRUST_MISS_TOLERANCE_DELTA,
            },
        }
    base = scenario_frame.loc[SCENARIO_BASE_CORE_ONLY]
    interaction = scenario_frame.loc[SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION]
    target_stock = scenario_frame.loc[SCENARIO_BASE_CORE_PLUS_TARGET_STOCK]
    allocation = scenario_frame.loc[SCENARIO_BASE_CORE_PLUS_ALLOCATION]
    micro_market = scenario_frame.loc[SCENARIO_BASE_CORE_PLUS_MICRO_MARKET]

    interaction_delta = float(interaction["delta_vs_base_promo_safe_pct_error"])
    interaction_mae_delta = float(interaction["delta_vs_base_mae_units"])
    micro_delta = float(micro_market["delta_vs_base_promo_safe_pct_error"])
    micro_mae_delta = float(micro_market["delta_vs_base_mae_units"])

    interaction_store = store_frame.loc[
        store_frame["scenario_id"].eq(SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION)
    ].copy()
    base_store = store_frame.loc[store_frame["scenario_id"].eq(SCENARIO_BASE_CORE_ONLY)].copy()
    micro_store = store_frame.loc[
        store_frame["scenario_id"].eq(SCENARIO_BASE_CORE_PLUS_MICRO_MARKET)
    ].copy()
    robustness = interaction_store.merge(
        base_store.loc[:, ["store_number", "promo_safe_pct_error", "mae_units"]].rename(
            columns={
                "promo_safe_pct_error": "base_promo_safe_pct_error",
                "mae_units": "base_mae_units",
            }
        ),
        on="store_number",
        how="left",
    ).merge(
        micro_store.loc[:, ["store_number", "promo_safe_pct_error", "mae_units"]].rename(
            columns={
                "promo_safe_pct_error": "micro_promo_safe_pct_error",
                "mae_units": "micro_mae_units",
            }
        ),
        on="store_number",
        how="left",
    )
    robustness["promo_safe_pct_error_improved_vs_base"] = (
        robustness["promo_safe_pct_error"].astype(float)
        < robustness["base_promo_safe_pct_error"].astype(float)
    )
    robustness["mae_improved_vs_base"] = (
        robustness["mae_units"].astype(float) < robustness["base_mae_units"].astype(float)
    )
    robustness["promo_safe_pct_error_improved_vs_full_micro"] = (
        robustness["promo_safe_pct_error"].astype(float)
        < robustness["micro_promo_safe_pct_error"].astype(float)
    )
    store_improvement_share = (
        round(float(robustness["promo_safe_pct_error_improved_vs_base"].mean()), 4)
        if not robustness.empty
        else 0.0
    )
    store_improvement_vs_micro_share = (
        round(float(robustness["promo_safe_pct_error_improved_vs_full_micro"].mean()), 4)
        if not robustness.empty
        else 0.0
    )

    base_sparse_error = float(segment_metrics[SCENARIO_BASE_CORE_ONLY]["sparse"]["promo_safe_pct_error"])
    interaction_sparse_error = float(
        segment_metrics[SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION]["sparse"]["promo_safe_pct_error"]
    )
    base_basket_led_error = float(
        segment_metrics[SCENARIO_BASE_CORE_ONLY]["basket_led"]["promo_safe_pct_error"]
    )
    interaction_basket_led_error = float(
        segment_metrics[SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION]["basket_led"]["promo_safe_pct_error"]
    )

    interaction_beats_base = (
        interaction_delta <= PROMO_SAFE_PCT_ERROR_IMPROVEMENT_THRESHOLD
        and interaction_mae_delta <= 0.0
        and float(interaction["delta_vs_base_trust_floor_miss_rate"]) <= TRUST_MISS_TOLERANCE_DELTA
        and store_improvement_share >= STORE_IMPROVEMENT_SHARE_THRESHOLD
    )
    interaction_beats_full_micro = (
        float(interaction["promo_safe_pct_error"]) <= float(micro_market["promo_safe_pct_error"])
        and float(interaction["mae_units"]) <= float(micro_market["mae_units"])
        and store_improvement_vs_micro_share >= STORE_IMPROVEMENT_SHARE_THRESHOLD
    )

    if interaction_beats_base and interaction_beats_full_micro:
        recommendation = "promote_interaction_bundle_later"
    elif interaction_beats_base:
        recommendation = "keep_under_watch"
    else:
        recommendation = "keep_downstream_only"

    return {
        "recommendation": recommendation,
        "interaction_bundle": {
            "scenario_id": SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION,
            "feature_columns": list(MICRO_INTERACTION_FEATURE_COLUMNS),
            "helps_vs_base": interaction_beats_base,
            "helps_vs_full_micro_family": interaction_beats_full_micro,
            "delta_vs_base_promo_safe_pct_error": interaction_delta,
            "delta_vs_base_mae_units": interaction_mae_delta,
            "delta_vs_full_micro_promo_safe_pct_error": float(
                interaction["promo_safe_pct_error"] - micro_market["promo_safe_pct_error"]
            ),
            "delta_vs_full_micro_mae_units": float(interaction["mae_units"] - micro_market["mae_units"]),
        },
        "full_micro_family": {
            "scenario_id": SCENARIO_BASE_CORE_PLUS_MICRO_MARKET,
            "helps_vs_base": micro_delta <= PROMO_SAFE_PCT_ERROR_IMPROVEMENT_THRESHOLD
            and micro_mae_delta <= 0.0,
            "delta_vs_base_promo_safe_pct_error": micro_delta,
            "delta_vs_base_mae_units": micro_mae_delta,
        },
        "downstream_addbacks": {
            "target_stock_shape": {
                "scenario_id": SCENARIO_BASE_CORE_PLUS_TARGET_STOCK,
                "delta_vs_base_promo_safe_pct_error": float(
                    target_stock["delta_vs_base_promo_safe_pct_error"]
                ),
                "delta_vs_base_mae_units": float(target_stock["delta_vs_base_mae_units"]),
            },
            "allocation_discipline": {
                "scenario_id": SCENARIO_BASE_CORE_PLUS_ALLOCATION,
                "delta_vs_base_promo_safe_pct_error": float(
                    allocation["delta_vs_base_promo_safe_pct_error"]
                ),
                "delta_vs_base_mae_units": float(allocation["delta_vs_base_mae_units"]),
            },
        },
        "store_robustness": {
            "interaction_store_improvement_share_vs_base": store_improvement_share,
            "interaction_store_improvement_share_vs_full_micro": store_improvement_vs_micro_share,
            "robust_across_stores": store_improvement_share >= STORE_IMPROVEMENT_SHARE_THRESHOLD,
            "store_count": int(len(robustness.index)),
        },
        "segment_lift": {
            "interaction_sparse_delta_vs_base_pct_error": interaction_sparse_error - base_sparse_error,
            "interaction_basket_led_delta_vs_base_pct_error": (
                interaction_basket_led_error - base_basket_led_error
            ),
        },
        "reference_scenarios": {
            "base_core_only": {
                "scenario_id": SCENARIO_BASE_CORE_ONLY,
                "promo_safe_pct_error": float(base["promo_safe_pct_error"]),
            },
            "base_core_plus_micro_interaction": {
                "scenario_id": SCENARIO_BASE_CORE_PLUS_MICRO_INTERACTION,
                "promo_safe_pct_error": float(interaction["promo_safe_pct_error"]),
            },
            "base_core_plus_target_stock_shape": {
                "scenario_id": SCENARIO_BASE_CORE_PLUS_TARGET_STOCK,
                "promo_safe_pct_error": float(target_stock["promo_safe_pct_error"]),
            },
            "base_core_plus_allocation_discipline": {
                "scenario_id": SCENARIO_BASE_CORE_PLUS_ALLOCATION,
                "promo_safe_pct_error": float(allocation["promo_safe_pct_error"]),
            },
            "base_core_plus_micro_market_equilibrium": {
                "scenario_id": SCENARIO_BASE_CORE_PLUS_MICRO_MARKET,
                "promo_safe_pct_error": float(micro_market["promo_safe_pct_error"]),
            },
        },
        "candidate_columns_for_later_promotion": (
            list(MICRO_INTERACTION_FEATURE_COLUMNS)
            if recommendation == "promote_interaction_bundle_later"
            else []
        ),
        "promotion_risks": [
            "interaction bundle may still proxy field composition rather than true incremental demand",
            "micro-market add-backs can improve paired rows while remaining unstable as always-on forecasters",
            "downstream trust and capital families should not re-enter the units head without repeat evidence",
        ],
        "acceptance_thresholds": {
            "promo_safe_pct_error_improvement_vs_base_max": PROMO_SAFE_PCT_ERROR_IMPROVEMENT_THRESHOLD,
            "store_improvement_share_min": STORE_IMPROVEMENT_SHARE_THRESHOLD,
            "trust_floor_miss_rate_delta_max": TRUST_MISS_TOLERANCE_DELTA,
        },
    }


def run_feature_family_ablation(
    *,
    run_id: str,
    artifact_paths: PromotionArtifactPaths,
    output_root: Path,
) -> FeatureFamilyAblationArtifacts:
    dataset, dataset_path, manifest_payload, manifest_path = _load_dataset_and_manifest(
        run_id=run_id,
        artifact_paths=artifact_paths,
    )
    manifest_feature_columns = tuple(
        str(column_name)
        for column_name in manifest_payload.get("feature_columns", [])
        if str(column_name)
    )
    manifest_target_columns = tuple(
        str(column_name)
        for column_name in manifest_payload.get("target_columns", [])
        if str(column_name)
    )
    missing_targets = [column_name for column_name in manifest_target_columns if column_name not in dataset.columns]
    if missing_targets:
        raise PromotionFeatureFamilyAblationError(
            "Training dataset is missing manifest-declared target columns.",
            details={"missing_target_columns": missing_targets},
        )

    scenarios = build_feature_family_ablation_scenarios(manifest_feature_columns)
    output_root.mkdir(parents=True, exist_ok=True)
    trainer = PromotionModelTrainer()
    split = trainer._time_splitter.split(dataset)
    full_source_context = _test_source_context(dataset, split.test_mask)
    full_test_source_rows = dataset.loc[split.test_mask].copy().reset_index(drop=True)

    control_row_keys: tuple[str, ...] | None = None
    summary_rows: list[dict[str, object]] = []
    promo_type_rows: list[dict[str, object]] = []
    store_rows: list[dict[str, object]] = []
    sparse_breakdown_rows: list[dict[str, object]] = []
    trust_capital_rows: list[dict[str, object]] = []
    segment_metrics: dict[str, dict[str, dict[str, float | int]]] = {}
    partial_summary_csv_path = output_root / "family_ablation_summary.partial.csv"

    for scenario in scenarios:
        scenario_start = perf_counter()
        print(
            f"feature_family_ablation_scenario_start: {scenario.scenario_id}",
            file=sys.stderr,
            flush=True,
        )
        heartbeat_stop, heartbeat_thread = _scenario_heartbeat_handle(scenario.scenario_id)
        heartbeat_thread.start()
        scenario_dataset = _scenario_dataset(dataset, scenario)
        try:
            if len(scenario_dataset.index) != len(dataset.index):
                raise PromotionFeatureFamilyAblationError(
                    "Feature-family ablation scenario changed the dataset row set.",
                    details={"scenario_id": scenario.scenario_id},
                )
            for target_column in manifest_target_columns:
                if target_column not in scenario_dataset.columns:
                    raise PromotionFeatureFamilyAblationError(
                        "Feature-family ablation scenario changed the target contract.",
                        details={"scenario_id": scenario.scenario_id, "missing_target_column": target_column},
                    )

            model_input, schema = prepare_model_input_frame(
                scenario_dataset,
                feature_columns=scenario.feature_columns,
            )
            tree_model = trainer._build_tree_regressor(schema)
            train_features = model_input.loc[split.train_mask]
            train_target = scenario_dataset.loc[split.train_mask, "target_actual_units_sold"]
            tree_model.fit(train_features, train_target)

            predictions = _build_test_predictions_frame(
                dataset=scenario_dataset,
                model_input=model_input,
                test_mask=split.test_mask,
                units_model=tree_model,
            )
            row_keys = tuple(predictions["promotion_row_key"].astype(str).tolist())
            if control_row_keys is None:
                control_row_keys = row_keys
            elif row_keys != control_row_keys:
                raise PromotionFeatureFamilyAblationError(
                    "Feature-family ablation scenarios produced different completed-promotion row sets.",
                    details={"scenario_id": scenario.scenario_id},
                )

            evaluation_rows, backtest_summary, scorecard_summary = _evaluation_rows(
                predictions=predictions,
                source_frame=full_test_source_rows,
                source_context=full_source_context,
            )
            runtime_seconds = perf_counter() - scenario_start
            summary_rows.append(
                _scenario_summary_row(
                    scenario=scenario,
                    feature_count=len(scenario.feature_columns),
                    model_input_feature_count=len(schema.feature_columns),
                    backtest_summary=backtest_summary,
                    scorecard_summary=scorecard_summary,
                    evaluation_rows=evaluation_rows,
                    runtime_seconds=runtime_seconds,
                )
            )
            pd.DataFrame(summary_rows).to_csv(partial_summary_csv_path, index=False)
            print(
                (
                    "feature_family_ablation_scenario_complete: "
                    f"{scenario.scenario_id} rows={int(len(evaluation_rows.index))} runtime_seconds={runtime_seconds:.2f}"
                ),
                file=sys.stderr,
                flush=True,
            )
            promo_type_rows.extend(_promo_type_breakdown_rows(scenario_id=scenario.scenario_id, evaluation_rows=evaluation_rows))
            store_rows.extend(_store_level_rows(scenario_id=scenario.scenario_id, evaluation_rows=evaluation_rows))
            segment_metrics[scenario.scenario_id] = _segment_summary_rows(evaluation_rows)
            sparse_breakdown_rows.extend(
                _segment_breakdown_rows(
                    scenario_id=scenario.scenario_id,
                    segment_metrics=segment_metrics[scenario.scenario_id],
                    segment_names=("sparse", "dense"),
                )
            )
            trust_capital_rows.extend(
                _segment_breakdown_rows(
                    scenario_id=scenario.scenario_id,
                    segment_metrics=segment_metrics[scenario.scenario_id],
                    segment_names=("trust_floor", "capital_efficiency"),
                )
            )
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=0.1)

    summary_frame = pd.DataFrame(summary_rows)
    summary_frame = _with_deltas(summary_frame, control_id="control_full_model_visible", base_id=SCENARIO_BASE_CORE_ONLY)
    control_by_store = pd.DataFrame(store_rows)
    control_store = control_by_store.loc[control_by_store["scenario_id"].eq("control_full_model_visible")].copy()
    control_store = control_store.rename(
        columns={
            "mae_units": "control_mae_units",
            "promo_safe_pct_error": "control_promo_safe_pct_error",
            "trust_floor_miss_rate": "control_trust_floor_miss_rate",
            "over_allocation_capital_drag_dollars_mean": "control_over_allocation_capital_drag_dollars_mean",
            "end_shape_success_rate": "control_end_shape_success_rate",
            "effective_sharpe_like_gp_per_drag_mean": "control_effective_sharpe_like_gp_per_drag_mean",
        }
    )
    store_frame = pd.DataFrame(store_rows).merge(
        control_store.loc[
            :,
            [
                "store_number",
                "control_mae_units",
                "control_promo_safe_pct_error",
                "control_trust_floor_miss_rate",
                "control_over_allocation_capital_drag_dollars_mean",
                "control_end_shape_success_rate",
                "control_effective_sharpe_like_gp_per_drag_mean",
            ],
        ],
        on="store_number",
        how="left",
    )
    for metric_name in (
        "mae_units",
        "promo_safe_pct_error",
        "trust_floor_miss_rate",
        "over_allocation_capital_drag_dollars_mean",
        "end_shape_success_rate",
        "effective_sharpe_like_gp_per_drag_mean",
    ):
        store_frame[f"delta_vs_control_{metric_name}"] = store_frame[metric_name].astype(float) - store_frame[f"control_{metric_name}"].astype(float)

    conclusion_payload = _ranked_conclusion(
        summary_rows=summary_frame,
        segment_metrics=segment_metrics,
        store_frame=store_frame,
    )

    summary_csv_path = output_root / "family_ablation_summary.csv"
    summary_json_path = output_root / "family_ablation_summary.json"
    promo_type_breakdown_csv_path = output_root / "family_ablation_promo_type_breakdown.csv"
    store_level_robustness_csv_path = output_root / "family_ablation_store_level_robustness.csv"
    sparse_demand_breakdown_csv_path = output_root / "family_ablation_sparse_demand_breakdown.csv"
    trust_capital_breakdown_csv_path = output_root / "family_ablation_trust_capital_breakdown.csv"
    conclusion_json_path = output_root / "family_ablation_conclusion.json"
    runtime_manifest_json_path = output_root / "family_ablation_runtime_manifest.json"

    summary_frame.to_csv(summary_csv_path, index=False)
    pd.DataFrame(promo_type_rows).to_csv(promo_type_breakdown_csv_path, index=False)
    store_frame.to_csv(store_level_robustness_csv_path, index=False)
    pd.DataFrame(sparse_breakdown_rows).to_csv(sparse_demand_breakdown_csv_path, index=False)
    pd.DataFrame(trust_capital_rows).to_csv(trust_capital_breakdown_csv_path, index=False)
    conclusion_json_path.write_text(json.dumps(conclusion_payload, indent=2, sort_keys=True), encoding="utf-8")
    summary_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "dataset_path": str(dataset_path),
                "dataset_manifest_path": str(manifest_path),
                "diagnostics_only": True,
                "target_columns": list(manifest_target_columns),
                "scenario_rows": summary_frame.to_dict(orient="records"),
                "sparse_demand_breakdown_rows": sparse_breakdown_rows,
                "trust_capital_breakdown_rows": trust_capital_rows,
                "segment_metrics": segment_metrics,
                "ranked_conclusion": conclusion_payload,
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    runtime_manifest_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "dataset_path": str(dataset_path),
                "dataset_manifest_path": str(manifest_path),
                "output_files": {
                    "family_ablation_summary_csv": str(summary_csv_path),
                    "family_ablation_summary_json": str(summary_json_path),
                    "family_ablation_promo_type_breakdown_csv": str(promo_type_breakdown_csv_path),
                    "family_ablation_store_level_robustness_csv": str(store_level_robustness_csv_path),
                    "family_ablation_sparse_demand_breakdown_csv": str(sparse_demand_breakdown_csv_path),
                    "family_ablation_trust_capital_breakdown_csv": str(trust_capital_breakdown_csv_path),
                    "family_ablation_conclusion_json": str(conclusion_json_path),
                    "family_ablation_partial_summary_csv": str(partial_summary_csv_path),
                },
                "scenario_manifest": [asdict(scenario) for scenario in scenarios],
                "row_set_guard": {
                    "compared_row_count": int(len(control_row_keys or ())),
                    "target_columns": list(manifest_target_columns),
                },
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    return FeatureFamilyAblationArtifacts(
        output_root=str(output_root),
        summary_csv_path=str(summary_csv_path),
        summary_json_path=str(summary_json_path),
        promo_type_breakdown_csv_path=str(promo_type_breakdown_csv_path),
        store_level_robustness_csv_path=str(store_level_robustness_csv_path),
        sparse_demand_breakdown_csv_path=str(sparse_demand_breakdown_csv_path),
        trust_capital_breakdown_csv_path=str(trust_capital_breakdown_csv_path),
        conclusion_json_path=str(conclusion_json_path),
        runtime_manifest_json_path=str(runtime_manifest_json_path),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    artifact_paths = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
    )
    output_root = (
        Path(args.output_root)
        if args.output_root
        else artifact_paths.inspection_run_root(args.run_id) / "feature_family_ablation"
    )
    artifacts = run_feature_family_ablation(
        run_id=args.run_id,
        artifact_paths=artifact_paths,
        output_root=output_root,
    )
    print(json.dumps(asdict(artifacts), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())