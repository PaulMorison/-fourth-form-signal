from __future__ import annotations

"""Diagnostics-only low-nonzero-demand specialist modeling pass."""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from models.promotions.low_nonzero_specialist import (
    LowNonzeroSpecialistBundleArtifacts,
    LowNonzeroSpecialistClassifierDiagnostics,
    LowNonzeroSpecialistConfig,
    build_lightgbm_regressor,
    build_low_nonzero_mask,
    build_specialist_model_input,
    compute_backtest_like_metrics,
    evaluate_multiclass_classifier,
    fit_binary_classifier_or_constant,
    fit_multiclass_classifier_or_constant,
    map_publishability_labels,
    persist_specialist_bundle,
    resolve_specialist_feature_columns,
    specialist_feature_family_names,
)
from models.promotions.model_bundle import read_json, write_json
from models.promotions.promotion_demand_backtest import compute_backtest_rows
from models.promotions.time_split import PromotionTimeSplitter
from models.promotions.trainer import PromotionModelTrainer
from runtime.promotions.artifact_compatibility import assert_artifact_compatibility
from runtime.promotions.artifact_locator import resolve_model_bundle, resolve_training_ready_artifact
from runtime.promotions.config import PromotionArtifactPaths
from runtime.promotions.decision_surface_service import load_training_ready_artifact, score_training_ready_rows
from runtime.promotions.run_promotions_decision_surface import _run_decision_surface_from_frames
from state.promotions.feature_engineering.demand.ft_allocation_discipline import (
    _build_trust_floor_capital_metrics,
    _build_weak_promo_low_value_flag,
)
from surfaces.promotions.reporting.store_prediction_download_builder import (
    PromotionStorePredictionDownloadBuilder,
    _prepare_feature_inspection_source_frame,
)
from surfaces.promotions.reporting.store_prediction_publisher import StorePredictionPublisher


SPECIALIST_RUNTIME_VERSION = "low_nonzero_specialist_v1"
SPECIALIST_FUTURE_SCORE_SUFFIX = "-score"
SCENARIO_CURRENT_SLIM = "current_slim_head"
SCENARIO_SPECIALIST = "specialist_low_nonzero_head"
SCENARIO_GATED = "gated_low_nonzero_strategy"
SHADOW_JOIN_KEYS = ("store_number", "promotion_header_key", "sku_number")
SHADOW_GROUP_DIMENSIONS = {
    "recommendation_reason": "baseline_recommendation_reason",
    "publishability_bucket": "baseline_publish_bucket",
    "demand_evidence_class": "baseline_demand_evidence_class",
    "sparse_history_flag": "sparse_history_flag",
    "trust_floor_risk_flag": "trust_floor_risk_flag",
    "stock_gap_flag": "stock_gap_flag",
    "store": "store_number",
    "promo_type": "promo_type",
}
VALUE_SHADOW_GROUP_DIMENSIONS = {
    "recommendation_reason": "recommendation_reason",
    "publishability_bucket": "publish_bucket",
    "demand_evidence_class": "demand_evidence_class",
    "sparse_history_flag": "sparse_history_flag",
    "trust_floor_risk_flag": "trust_floor_risk_flag",
    "stock_gap_flag": "stock_gap_flag",
    "store": "store_number",
    "promo_type": "promo_type",
}
SPARSE_HISTORY_DEMAND_CLASSES = frozenset({"cold_start", "insufficient_history", "sparse_history"})
MATERIAL_RAW_PREDICTED_UNITS_DELTA_MIN = 0.10
MATERIAL_RAW_CONFIDENCE_DELTA_MIN = 0.02
COMMERCIAL_THRESHOLD_UNIT_DELTA_MIN = 1.0
COMMERCIAL_THRESHOLD_CONFIDENCE_DELTA_MIN = 0.05
COMMERCIAL_THRESHOLD_VALUE_DELTA_MIN = 0.50
PUBLISH_CONFIDENCE_FLOOR = 0.45
VALUE_SHADOW_VALUE_DELTA_MIN = 0.01
VALUE_SHADOW_LOW_VALUE_REASON = "value_shadow_low_incremental_value"
VALUE_SHADOW_RELIEVED_REASON = "value_shadow_value_relief"


@dataclass(frozen=True)
class LowNonzeroScenarioSummary:
    scenario_id: str
    scenario_kind: str
    model_bundle_path: str
    feature_family_names: tuple[str, ...]
    evaluation_row_count: int
    evaluation_low_nonzero_row_count: int
    mae: float | None
    mape: float | None
    overforecast_rate: float | None
    low_nonzero_mae: float | None
    low_nonzero_mape: float | None
    low_nonzero_overforecast_rate: float | None
    publish_eligible_row_count: int
    review_only_row_count: int
    excluded_legitimate_row_count: int
    do_not_order_low_incremental_value_row_count: int
    low_nonzero_gate_row_count: int


@dataclass(frozen=True)
class LowNonzeroSpecialistRunArtifacts:
    output_root: str
    runtime_manifest_path: str
    scenario_summary_csv_path: str
    scenario_summary_json_path: str
    classifier_summary_json_path: str
    classifier_summary_csv_path: str
    recommendation_md_path: str
    specialist_bundle_path: str
    shadow_vs_baseline_row_deltas_csv_path: str
    shadow_vs_baseline_reason_transitions_csv_path: str
    shadow_vs_baseline_threshold_blockers_csv_path: str
    shadow_vs_baseline_summary_json_path: str
    shadow_vs_baseline_brief_md_path: str
    specialist_value_shadow_row_deltas_csv_path: str
    specialist_value_shadow_reason_transitions_csv_path: str
    specialist_value_shadow_summary_json_path: str
    specialist_value_shadow_brief_md_path: str
    specialist_value_shadow_flip_candidates_csv_path: str


@dataclass(frozen=True)
class LowNonzeroShadowAttributionArtifacts:
    row_deltas_csv_path: str
    reason_transitions_csv_path: str
    threshold_blockers_csv_path: str
    summary_json_path: str
    brief_md_path: str


@dataclass(frozen=True)
class LowNonzeroValueShadowArtifacts:
    row_deltas_csv_path: str
    reason_transitions_csv_path: str
    summary_json_path: str
    brief_md_path: str
    flip_candidates_csv_path: str


class PromotionLowNonzeroSpecialistError(ValueError):
    """Raised when the governed low-nonzero specialist diagnostics contract fails."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run diagnostics-only low-nonzero-demand specialist model comparisons for governed promotions datasets."
    )
    parser.add_argument("--run-id", required=True, help="Training dataset run id used for the specialist diagnostics pass.")
    parser.add_argument("--future-score-run-id", help="Future scoring run id. Defaults to <run-id>-score.")
    parser.add_argument("--baseline-model-run-id", help="Baseline slim-head model run id. Defaults to --run-id.")
    parser.add_argument("--artifact-root", help="Override governed promotions artifact root.")
    parser.add_argument("--output-root", help="Override diagnostics output root. Defaults to model_family/<run-id>/low_nonzero_specialist_diagnostics.")
    parser.add_argument("--as-of-date", help="Decision-surface as-of date. Defaults to dataset manifest or today.")
    parser.add_argument("--local-inspection-root", help="Optional local inspection root containing an existing decision-surface CSV for the run.")
    parser.add_argument("--future-decision-surface-csv-path", help="Optional explicit decision-surface CSV path to use as the future comparison base.")
    parser.add_argument("--enable-optional-family", action="append", default=[], help="Optional downstream family to include in the specialist head.")
    parser.add_argument("--quantile-alpha", type=float, default=0.35, help="Conservative LightGBM quantile alpha (<0.5 penalizes overforecasting more).")
    parser.add_argument("--minimum-cohort-sample-size", type=int, default=25)
    parser.add_argument("--similarity-threshold", type=float, default=0.25)
    parser.add_argument("--archetype-confidence-floor", type=float, default=0.10)
    parser.add_argument("--row-model-confidence-floor", type=float, default=0.10)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = LowNonzeroSpecialistConfig(
        quantile_alpha=float(args.quantile_alpha),
        enabled_optional_families=tuple(args.enable_optional_family),
    )
    artifacts = run_low_nonzero_specialist_diagnostics(
        run_id=args.run_id,
        future_score_run_id=args.future_score_run_id,
        baseline_model_run_id=args.baseline_model_run_id,
        artifact_root=args.artifact_root,
        output_root=args.output_root,
        as_of_date=args.as_of_date,
        local_inspection_root=args.local_inspection_root,
        future_decision_surface_csv_path=args.future_decision_surface_csv_path,
        config=config,
        minimum_cohort_sample_size=args.minimum_cohort_sample_size,
        similarity_threshold=args.similarity_threshold,
        archetype_confidence_floor=args.archetype_confidence_floor,
        row_model_confidence_floor=args.row_model_confidence_floor,
    )
    print(json.dumps(asdict(artifacts), indent=2, sort_keys=True))
    return 0


def run_low_nonzero_specialist_diagnostics(
    *,
    run_id: str,
    future_score_run_id: str | None,
    baseline_model_run_id: str | None,
    artifact_root: str | None,
    output_root: str | None,
    as_of_date: str | None,
    local_inspection_root: str | None,
    future_decision_surface_csv_path: str | None,
    config: LowNonzeroSpecialistConfig,
    minimum_cohort_sample_size: int,
    similarity_threshold: float | None,
    archetype_confidence_floor: float | None,
    row_model_confidence_floor: float | None,
) -> LowNonzeroSpecialistRunArtifacts:
    artifact_paths = PromotionArtifactPaths.from_env(root=Path(artifact_root) if artifact_root else None)
    dataset_artifact = resolve_training_ready_artifact(
        artifact_paths=artifact_paths,
        dataset_run_id=run_id,
    )
    dataset = load_training_ready_artifact(dataset_artifact.dataset_path).frame
    if dataset.empty:
        raise PromotionLowNonzeroSpecialistError("Training dataset is empty.")

    resolved_as_of_date = _resolve_as_of_date(as_of_date, dataset_artifact.manifest)
    output_root_path = Path(output_root) if output_root else artifact_paths.model_family_root(run_id) / "low_nonzero_specialist_diagnostics"
    output_root_path.mkdir(parents=True, exist_ok=True)

    baseline_bundle = _resolve_or_train_baseline_bundle(
        run_id=run_id,
        baseline_model_run_id=baseline_model_run_id,
        dataset=dataset,
        dataset_path=dataset_artifact.dataset_path,
        artifact_paths=artifact_paths,
        output_root=output_root_path,
    )
    baseline_bundle_root = Path(baseline_bundle.model_bundle_path)

    specialist_feature_columns = resolve_specialist_feature_columns(config=config)
    specialist_model_input, specialist_schema = build_specialist_model_input(dataset, config=config)
    split = PromotionTimeSplitter().split(dataset)

    realized_low_nonzero_mask = build_low_nonzero_mask(dataset["target_actual_units_sold"])
    specialist_train_mask = split.train_mask & realized_low_nonzero_mask
    if int(specialist_train_mask.sum()) < int(minimum_cohort_sample_size):
        raise PromotionLowNonzeroSpecialistError(
            "Low-nonzero specialist cohort is too small to train governed diagnostics.",
            details={
                "train_low_nonzero_rows": int(specialist_train_mask.sum()),
                "train_rows": int(split.train_mask.sum()),
                "minimum_cohort_sample_size": int(minimum_cohort_sample_size),
            },
        )

    units_specialist = build_lightgbm_regressor(specialist_schema, config=config)
    units_specialist.fit(
        specialist_model_input.loc[specialist_train_mask],
        dataset.loc[specialist_train_mask, "target_actual_units_sold"],
    )
    gross_profit_specialist = build_lightgbm_regressor(specialist_schema, config=config)
    gross_profit_specialist.fit(
        specialist_model_input.loc[specialist_train_mask],
        dataset.loc[specialist_train_mask, "target_actual_gross_profit_dollars"],
    )
    overallocation_specialist = fit_binary_classifier_or_constant(
        specialist_schema,
        specialist_model_input.loc[specialist_train_mask],
        dataset.loc[specialist_train_mask, "target_overallocation_flag"],
        config=config,
    )
    underallocation_specialist = fit_binary_classifier_or_constant(
        specialist_schema,
        specialist_model_input.loc[specialist_train_mask],
        dataset.loc[specialist_train_mask, "target_underallocation_flag"],
        config=config,
    )
    stockout_specialist = fit_binary_classifier_or_constant(
        specialist_schema,
        specialist_model_input.loc[specialist_train_mask],
        dataset.loc[specialist_train_mask, "target_stockout_flag"],
        config=config,
    )

    specialist_bundle_root = output_root_path / "bundles" / "low_nonzero_specialist"
    if (specialist_bundle_root / "run_manifest.json").exists() and (specialist_bundle_root / "inference_schema.json").exists():
        specialist_bundle = resolve_model_bundle(
            artifact_paths=artifact_paths,
            model_bundle_path=specialist_bundle_root,
        )
    else:
        specialist_metrics_payload = {
            "specialist_objective": f"lightgbm_quantile_alpha_{config.quantile_alpha}",
            "feature_families": list(specialist_feature_family_names(specialist_feature_columns)),
            "train_row_count": int(split.train_mask.sum()),
            "train_low_nonzero_row_count": int(specialist_train_mask.sum()),
        }
        specialist_bundle_artifacts = persist_specialist_bundle(
            run_id=f"{run_id}-low-nonzero-specialist-bundle",
            dataset_path=dataset_artifact.dataset_path,
            artifact_root=specialist_bundle_root,
            schema=specialist_schema,
            metrics=specialist_metrics_payload,
            units_model=units_specialist,
            gross_profit_model=gross_profit_specialist,
            overallocation_classifier=overallocation_specialist,
            underallocation_classifier=underallocation_specialist,
            stockout_classifier=stockout_specialist,
        )
        specialist_bundle = resolve_model_bundle(
            artifact_paths=artifact_paths,
            model_bundle_path=specialist_bundle_artifacts.bundle_root,
        )
    assert_artifact_compatibility(dataset_artifact=dataset_artifact, model_bundle=specialist_bundle)

    future_decision_surface_base = _resolve_future_decision_surface_base_frame(
        run_id=run_id,
        local_inspection_root=local_inspection_root,
        future_decision_surface_csv_path=future_decision_surface_csv_path,
    )

    baseline_hist = score_training_ready_rows(dataset.copy(), model_bundle_path=baseline_bundle.model_bundle_path).scored_frame
    specialist_hist = score_training_ready_rows(dataset.copy(), model_bundle_path=specialist_bundle.model_bundle_path).scored_frame

    future_score_run = future_score_run_id or f"{run_id}{SPECIALIST_FUTURE_SCORE_SUFFIX}"
    future_scored_source = pd.read_parquet(artifact_paths.scoring_rows_path(future_score_run))
    baseline_future = score_training_ready_rows(
        future_scored_source.copy(),
        model_bundle_path=baseline_bundle.model_bundle_path,
    ).scored_frame
    specialist_future = score_training_ready_rows(
        future_scored_source.copy(),
        model_bundle_path=specialist_bundle.model_bundle_path,
    ).scored_frame

    historical_gate_mask = build_low_nonzero_mask(dataset["target_actual_units_sold"]).reindex(dataset.index, fill_value=False)
    future_gate_mask = _future_low_nonzero_gate_mask(
        baseline_future=baseline_future,
        future_decision_surface_base=future_decision_surface_base,
    )
    gated_hist = _build_gated_scored_frame(
        baseline_hist,
        specialist_hist,
        gate_mask=historical_gate_mask.loc[baseline_hist.index],
    )
    gated_future = _build_gated_scored_frame(
        baseline_future,
        specialist_future,
        gate_mask=future_gate_mask,
    )

    evaluation_mask = split.validation_mask | split.test_mask
    scenario_summaries = []
    scenario_decision_surfaces: dict[str, pd.DataFrame] = {}
    baseline_backtest_rows = _build_scenario_backtest_rows(dataset.loc[evaluation_mask].copy(), baseline_hist.loc[evaluation_mask].copy())
    specialist_backtest_rows = _build_scenario_backtest_rows(dataset.loc[evaluation_mask].copy(), specialist_hist.loc[evaluation_mask].copy())
    gated_backtest_rows = _build_scenario_backtest_rows(dataset.loc[evaluation_mask].copy(), gated_hist.loc[evaluation_mask].copy())

    scenario_definitions = [
        (SCENARIO_CURRENT_SLIM, "baseline_current_slim", baseline_bundle, baseline_hist, baseline_future, baseline_backtest_rows),
        (SCENARIO_SPECIALIST, "specialist_only", specialist_bundle, specialist_hist, specialist_future, specialist_backtest_rows),
        (SCENARIO_GATED, "gated_strategy", specialist_bundle, gated_hist, gated_future, gated_backtest_rows),
    ]
    for scenario_id, scenario_kind, scenario_bundle, historical_scored_frame, future_scored_frame, backtest_rows in scenario_definitions:
        if future_decision_surface_base is not None:
            decision_surface_frame = _overlay_scored_predictions_on_decision_surface(
                base_decision_surface_frame=future_decision_surface_base,
                scored_frame=future_scored_frame,
            )
        else:
            decision_surface_frame = _run_decision_surface_scenario(
                artifact_paths=artifact_paths,
                dataset_artifact=dataset_artifact,
                model_bundle=scenario_bundle,
                run_id=f"{run_id}-{scenario_id}",
                as_of_date=resolved_as_of_date,
                historical_scored_frame=historical_scored_frame,
                future_scored_frame=future_scored_frame,
                minimum_cohort_sample_size=minimum_cohort_sample_size,
                similarity_threshold=similarity_threshold,
                archetype_confidence_floor=archetype_confidence_floor,
                row_model_confidence_floor=row_model_confidence_floor,
            )
        scenario_decision_surfaces[scenario_id] = decision_surface_frame.copy()
        publishability_summary = _summarize_publishability_from_decision_surface(
            run_id=f"{run_id}-{scenario_id}",
            as_of_date=resolved_as_of_date,
            decision_surface_frame=decision_surface_frame,
        )
        overall_metrics = compute_backtest_like_metrics(backtest_rows)
        low_nonzero_rows = backtest_rows.loc[build_low_nonzero_mask(backtest_rows["actual_units_sold_promo"])].copy()
        low_nonzero_metrics = compute_backtest_like_metrics(low_nonzero_rows)
        scenario_summaries.append(
            LowNonzeroScenarioSummary(
                scenario_id=scenario_id,
                scenario_kind=scenario_kind,
                model_bundle_path=scenario_bundle.model_bundle_path,
                feature_family_names=specialist_feature_family_names(resolve_specialist_feature_columns(config=config)) if scenario_id != SCENARIO_CURRENT_SLIM else specialist_feature_family_names(resolve_specialist_feature_columns(config=LowNonzeroSpecialistConfig())),
                evaluation_row_count=int(overall_metrics["row_count"] or 0),
                evaluation_low_nonzero_row_count=int(low_nonzero_metrics["row_count"] or 0),
                mae=_maybe_float(overall_metrics.get("mae")),
                mape=_maybe_float(overall_metrics.get("mape")),
                overforecast_rate=_maybe_float(overall_metrics.get("overforecast_rate")),
                low_nonzero_mae=_maybe_float(low_nonzero_metrics.get("mae")),
                low_nonzero_mape=_maybe_float(low_nonzero_metrics.get("mape")),
                low_nonzero_overforecast_rate=_maybe_float(low_nonzero_metrics.get("overforecast_rate")),
                publish_eligible_row_count=int(publishability_summary["publish_eligible_row_count"]),
                review_only_row_count=int(publishability_summary["review_only_row_count"]),
                excluded_legitimate_row_count=int(publishability_summary["excluded_legitimate_row_count"]),
                do_not_order_low_incremental_value_row_count=int(publishability_summary["do_not_order_low_incremental_value_row_count"]),
                low_nonzero_gate_row_count=int(future_gate_mask.sum()),
            )
        )

    classifier_diagnostics = _train_diagnostic_publishability_classifier(
        baseline_future=baseline_future,
        run_id=run_id,
        as_of_date=resolved_as_of_date,
        decision_surface_frame=future_decision_surface_base,
        config=config,
    )

    scenario_summary_frame = pd.DataFrame([asdict(row) for row in scenario_summaries])
    shadow_attribution = _write_shadow_vs_baseline_diagnostics(
        run_id=run_id,
        as_of_date=resolved_as_of_date,
        output_root=output_root_path,
        baseline_decision_surface_frame=scenario_decision_surfaces[SCENARIO_CURRENT_SLIM],
        shadow_decision_surface_frame=scenario_decision_surfaces[SCENARIO_GATED],
        baseline_scored_frame=baseline_future,
        shadow_scored_frame=gated_future,
        low_nonzero_gate_mask=future_gate_mask,
        scenario_summary_frame=scenario_summary_frame,
    )
    value_shadow = _write_specialist_value_shadow_diagnostics(
        run_id=run_id,
        as_of_date=resolved_as_of_date,
        output_root=output_root_path,
        baseline_decision_surface_frame=scenario_decision_surfaces[SCENARIO_CURRENT_SLIM],
        baseline_scored_frame=baseline_future,
        shadow_scored_frame=gated_future,
        low_nonzero_gate_mask=future_gate_mask,
        scenario_summary_frame=scenario_summary_frame,
    )
    scenario_summary_json_path = output_root_path / "scenario_comparison_summary.json"
    scenario_summary_csv_path = output_root_path / "scenario_comparison_summary.csv"
    classifier_summary_json_path = output_root_path / "specialist_action_classifier_summary.json"
    classifier_summary_csv_path = output_root_path / "specialist_action_classifier_summary.csv"
    recommendation_md_path = output_root_path / "low_nonzero_specialist_recommendation.md"
    runtime_manifest_path = output_root_path / "low_nonzero_specialist_runtime_manifest.json"

    scenario_summary_frame.to_csv(scenario_summary_csv_path, index=False)
    write_json(scenario_summary_json_path, {"rows": scenario_summary_frame.to_dict(orient="records")})
    classifier_summary_frame = pd.DataFrame([asdict(classifier_diagnostics)])
    classifier_summary_frame.to_csv(classifier_summary_csv_path, index=False)
    write_json(classifier_summary_json_path, asdict(classifier_diagnostics))

    recommendation = _build_recommendation_markdown(
        run_id=run_id,
        scenario_summary_frame=scenario_summary_frame,
        classifier_diagnostics=classifier_diagnostics,
        config=config,
    )
    recommendation_md_path.write_text(recommendation, encoding="utf-8")

    runtime_manifest = {
        "runtime_version": SPECIALIST_RUNTIME_VERSION,
        "run_id": run_id,
        "dataset_path": dataset_artifact.dataset_path,
        "future_score_run_id": future_score_run,
        "future_decision_surface_overlay_used": bool(future_decision_surface_base is not None),
        "baseline_model_bundle_path": baseline_bundle.model_bundle_path,
        "specialist_model_bundle_path": specialist_bundle.model_bundle_path,
        "feature_families": list(specialist_feature_family_names(resolve_specialist_feature_columns(config=config))),
        "quantile_alpha": config.quantile_alpha,
        "scenario_summary_csv_path": str(scenario_summary_csv_path),
        "scenario_summary_json_path": str(scenario_summary_json_path),
        "classifier_summary_json_path": str(classifier_summary_json_path),
        "classifier_summary_csv_path": str(classifier_summary_csv_path),
        "recommendation_md_path": str(recommendation_md_path),
        "shadow_vs_baseline_row_deltas_csv_path": shadow_attribution.row_deltas_csv_path,
        "shadow_vs_baseline_reason_transitions_csv_path": shadow_attribution.reason_transitions_csv_path,
        "shadow_vs_baseline_threshold_blockers_csv_path": shadow_attribution.threshold_blockers_csv_path,
        "shadow_vs_baseline_summary_json_path": shadow_attribution.summary_json_path,
        "shadow_vs_baseline_brief_md_path": shadow_attribution.brief_md_path,
        "specialist_value_shadow_row_deltas_csv_path": value_shadow.row_deltas_csv_path,
        "specialist_value_shadow_reason_transitions_csv_path": value_shadow.reason_transitions_csv_path,
        "specialist_value_shadow_summary_json_path": value_shadow.summary_json_path,
        "specialist_value_shadow_brief_md_path": value_shadow.brief_md_path,
        "specialist_value_shadow_flip_candidates_csv_path": value_shadow.flip_candidates_csv_path,
    }
    write_json(runtime_manifest_path, runtime_manifest)
    return LowNonzeroSpecialistRunArtifacts(
        output_root=str(output_root_path),
        runtime_manifest_path=str(runtime_manifest_path),
        scenario_summary_csv_path=str(scenario_summary_csv_path),
        scenario_summary_json_path=str(scenario_summary_json_path),
        classifier_summary_json_path=str(classifier_summary_json_path),
        classifier_summary_csv_path=str(classifier_summary_csv_path),
        recommendation_md_path=str(recommendation_md_path),
        specialist_bundle_path=specialist_bundle.model_bundle_path,
        shadow_vs_baseline_row_deltas_csv_path=shadow_attribution.row_deltas_csv_path,
        shadow_vs_baseline_reason_transitions_csv_path=shadow_attribution.reason_transitions_csv_path,
        shadow_vs_baseline_threshold_blockers_csv_path=shadow_attribution.threshold_blockers_csv_path,
        shadow_vs_baseline_summary_json_path=shadow_attribution.summary_json_path,
        shadow_vs_baseline_brief_md_path=shadow_attribution.brief_md_path,
        specialist_value_shadow_row_deltas_csv_path=value_shadow.row_deltas_csv_path,
        specialist_value_shadow_reason_transitions_csv_path=value_shadow.reason_transitions_csv_path,
        specialist_value_shadow_summary_json_path=value_shadow.summary_json_path,
        specialist_value_shadow_brief_md_path=value_shadow.brief_md_path,
        specialist_value_shadow_flip_candidates_csv_path=value_shadow.flip_candidates_csv_path,
    )


def _resolve_as_of_date(raw_as_of_date: str | None, dataset_manifest: dict[str, object]) -> str:
    if raw_as_of_date:
        return raw_as_of_date
    created = str(dataset_manifest.get("created_at_utc") or "").strip()
    if created:
        return str(pd.Timestamp(created).date())
    return str(date.today())


def _resolve_or_train_baseline_bundle(
    *,
    run_id: str,
    baseline_model_run_id: str | None,
    dataset: pd.DataFrame,
    dataset_path: str,
    artifact_paths: PromotionArtifactPaths,
    output_root: Path,
):
    target_run_id = baseline_model_run_id or run_id
    model_root = artifact_paths.model_family_root(target_run_id)
    if (model_root / "run_manifest.json").exists() and (model_root / "inference_schema.json").exists():
        return resolve_model_bundle(artifact_paths=artifact_paths, model_run_id=target_run_id)

    baseline_artifact_root = output_root / "bundles" / "current_slim_baseline"
    baseline_artifact_root.mkdir(parents=True, exist_ok=True)
    temp_artifact_paths = PromotionArtifactPaths(root=baseline_artifact_root.parent.parent)
    training_artifacts = PromotionModelTrainer().train(
        run_id=baseline_artifact_root.name,
        dataset=dataset,
        dataset_path=dataset_path,
        artifact_paths=temp_artifact_paths,
    )
    return resolve_model_bundle(
        artifact_paths=temp_artifact_paths,
        model_bundle_path=training_artifacts.artifact_root,
    )


def _run_decision_surface_scenario(
    *,
    artifact_paths: PromotionArtifactPaths,
    dataset_artifact,
    model_bundle,
    run_id: str,
    as_of_date: str,
    historical_scored_frame: pd.DataFrame,
    future_scored_frame: pd.DataFrame,
    minimum_cohort_sample_size: int,
    similarity_threshold: float | None,
    archetype_confidence_floor: float | None,
    row_model_confidence_floor: float | None,
) -> pd.DataFrame:
    compatibility_result = assert_artifact_compatibility(
        dataset_artifact=dataset_artifact,
        model_bundle=model_bundle,
    )
    artifacts = _run_decision_surface_from_frames(
        evaluation_scored_frame=future_scored_frame.copy(),
        historical_reference_frame=historical_scored_frame.copy(),
        use_backtest_matches_for_evaluation=False,
        artifact_paths=artifact_paths,
        run_id=run_id,
        decision_as_of_date=date.fromisoformat(as_of_date),
        minimum_cohort_sample_size=minimum_cohort_sample_size,
        similarity_threshold=similarity_threshold,
        archetype_confidence_floor=archetype_confidence_floor,
        row_model_confidence_floor=row_model_confidence_floor,
        resolved_dataset_artifact=dataset_artifact,
        resolved_model_bundle=model_bundle,
        compatibility_result=compatibility_result,
        evaluation_feature_column_count=int(
            len([column_name for column_name in future_scored_frame.columns if str(column_name).startswith("feature_")])
        ),
        operator_progress=None,
        decision_surface_stage_number=None,
        inspection_stage_number=None,
        total_stages=None,
    )
    decision_surface_parquet = Path(artifacts.report_paths["promotion_decision_surface"]["parquet"])
    return pd.read_parquet(decision_surface_parquet)


def _summarize_publishability_from_decision_surface(
    *,
    run_id: str,
    as_of_date: str,
    decision_surface_frame: pd.DataFrame,
) -> dict[str, object]:
    builder = PromotionStorePredictionDownloadBuilder()
    publisher = StorePredictionPublisher()
    download_frame = builder._build_download_frame(
        run_id=run_id,
        as_of_date=as_of_date,
        frame=decision_surface_frame,
    )
    review_input = _build_publish_review_input_frame(
        run_id=run_id,
        as_of_date=as_of_date,
        download_frame=download_frame,
    )
    review_frame = publisher._build_review_frame(review_input)
    annotated_review_frame = publisher._annotate_pos_eligibility(review_frame)
    class_counts = publisher._build_publish_eligibility_class_counts(annotated_review_frame)
    return {
        "publish_eligible_row_count": int(class_counts.get("publish_eligible", 0)),
        "review_only_row_count": int(class_counts.get("review_only", 0)),
        "excluded_legitimate_row_count": int(class_counts.get("excluded_legitimate", 0)),
        "do_not_order_low_incremental_value_row_count": int(
            annotated_review_frame["publish_eligibility_reason"].astype(str).eq("do_not_order_low_incremental_value").sum()
        ),
    }


def _build_publish_review_input_frame(
    *,
    run_id: str,
    as_of_date: str,
    download_frame: pd.DataFrame,
) -> pd.DataFrame:
    work = download_frame.copy()
    if "promotion_end_date" in work.columns and "promotion_break_date" not in work.columns:
        work["promotion_break_date"] = work["promotion_end_date"]
    if "recommended_order_quantity" not in work.columns:
        work["recommended_order_quantity"] = pd.to_numeric(
            work.get("suggested_order_units", work.get("recommended_order_units", 0.0)),
            errors="coerce",
        )
    if "target_soh_on_break_date" not in work.columns:
        work["target_soh_on_break_date"] = pd.to_numeric(
            work.get("promo_start_target_soh_units", 0.0),
            errors="coerce",
        )
    if "decision_action" not in work.columns:
        work["decision_action"] = work.get("decision_recommendation", "HOLD")
    if "confidence_score" not in work.columns:
        work["confidence_score"] = pd.to_numeric(
            work.get("final_confidence_score", 0.0),
            errors="coerce",
        )
    if "expected_sales_to_break_date" not in work.columns:
        work["expected_sales_to_break_date"] = pd.to_numeric(
            work.get("predicted_units_until_promo_start", work.get("predicted_units_sold", 0.0)),
            errors="coerce",
        )
    if "forecast_promo_units" not in work.columns:
        work["forecast_promo_units"] = pd.to_numeric(
            work.get("predicted_units_total_promo", work.get("predicted_units_sold", 0.0)),
            errors="coerce",
        )
    if "client_code" not in work.columns:
        work["client_code"] = "diagnostic"
    if "banner_code" not in work.columns:
        work["banner_code"] = work["client_code"]
    if "store_name" not in work.columns:
        work["store_name"] = work.get("store_name", pd.Series(work.get("store_number", ""), index=work.index)).astype(str)
    if "promotion_id" not in work.columns:
        work["promotion_id"] = work.get("promotion_header_key", work.get("promotional_sku_id_key", ""))
    if "model_version" not in work.columns:
        work["model_version"] = run_id
    if "prediction_run_id" not in work.columns:
        work["prediction_run_id"] = run_id
    if "prediction_created_at" not in work.columns:
        work["prediction_created_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    for column_name, default_value in (
        ("manual_review_flag", 0),
        ("review_required_flag", 0),
        ("store_mapping_resolved_flag", 1),
        ("store_mapping_active_flag", 1),
        ("store_mapping_error", ""),
        ("cold_start_flag", 0),
        ("insufficient_history_flag", 0),
    ):
        if column_name not in work.columns:
            work[column_name] = default_value
    if "current_soh" not in work.columns and "current_soh_units" in work.columns:
        work["current_soh"] = work["current_soh_units"]
    return work


def _resolve_future_decision_surface_base_frame(
    *,
    run_id: str,
    local_inspection_root: str | None,
    future_decision_surface_csv_path: str | None,
) -> pd.DataFrame | None:
    candidate_paths: list[Path] = []
    if future_decision_surface_csv_path:
        candidate_paths.append(Path(future_decision_surface_csv_path))
    if local_inspection_root:
        candidate_paths.append(Path(local_inspection_root) / run_id / f"{run_id}_decision_surface.csv")
    for candidate in candidate_paths:
        if candidate.exists():
            return pd.read_csv(candidate)
    return None


def _overlay_scored_predictions_on_decision_surface(
    *,
    base_decision_surface_frame: pd.DataFrame,
    scored_frame: pd.DataFrame,
) -> pd.DataFrame:
    overlay_columns = [
        column_name
        for column_name in (
            "promotion_row_key",
            "predicted_units_sold",
            "predicted_sales_ex_gst",
            "predicted_gross_profit_dollars",
            "predicted_sell_through_pct",
            "predicted_overallocation_risk",
            "predicted_underallocation_risk",
            "predicted_stockout_risk",
            "row_model_confidence_score",
        )
        if column_name in scored_frame.columns
    ]
    if "promotion_row_key" not in overlay_columns or "promotion_row_key" not in base_decision_surface_frame.columns:
        return base_decision_surface_frame.copy()
    overlay = scored_frame.loc[:, overlay_columns].copy()
    merged = base_decision_surface_frame.drop(
        columns=[
            column_name
            for column_name in overlay_columns
            if column_name != "promotion_row_key" and column_name in base_decision_surface_frame.columns
        ],
        errors="ignore",
    ).merge(overlay, on="promotion_row_key", how="left")
    return merged


def _build_gated_scored_frame(
    baseline_frame: pd.DataFrame,
    specialist_frame: pd.DataFrame,
    *,
    gate_mask: pd.Series,
) -> pd.DataFrame:
    gated = baseline_frame.copy()
    aligned_gate_mask = gate_mask.reindex(gated.index, fill_value=False).astype(bool)
    for column_name in (
        "predicted_units_sold",
        "predicted_sales_ex_gst",
        "predicted_gross_profit_dollars",
        "predicted_sell_through_pct",
        "predicted_overallocation_risk",
        "predicted_underallocation_risk",
        "predicted_stockout_risk",
        "row_model_confidence_score",
    ):
        if column_name not in gated.columns or column_name not in specialist_frame.columns:
            continue
        gated.loc[aligned_gate_mask, column_name] = specialist_frame.loc[aligned_gate_mask, column_name]
    return gated


def _future_low_nonzero_gate_mask(
    *,
    baseline_future: pd.DataFrame,
    future_decision_surface_base: pd.DataFrame | None,
) -> pd.Series:
    if future_decision_surface_base is not None and "demand_evidence_class" in future_decision_surface_base.columns:
        return future_decision_surface_base["demand_evidence_class"].fillna("").astype(str).str.strip().str.lower().eq("low_nonzero_demand")
    return build_low_nonzero_mask(baseline_future["predicted_units_sold"])


def _build_scenario_backtest_rows(dataset_slice: pd.DataFrame, scored_slice: pd.DataFrame) -> pd.DataFrame:
    backtest_frame = dataset_slice.copy()
    backtest_frame["predicted_units_total_promo"] = pd.to_numeric(
        scored_slice["predicted_units_sold"],
        errors="coerce",
    ).fillna(0.0)
    if "actual_units_sold_promo" not in backtest_frame.columns:
        backtest_frame["actual_units_sold_promo"] = pd.to_numeric(
            backtest_frame.get("target_actual_units_sold"),
            errors="coerce",
        ).fillna(0.0)
    return compute_backtest_rows(backtest_frame)


def _train_diagnostic_publishability_classifier(
    *,
    baseline_future: pd.DataFrame,
    run_id: str,
    as_of_date: str,
    decision_surface_frame: pd.DataFrame | None,
    config: LowNonzeroSpecialistConfig,
) -> LowNonzeroSpecialistClassifierDiagnostics:
    builder = PromotionStorePredictionDownloadBuilder()
    publisher = StorePredictionPublisher()
    source_frame = decision_surface_frame.copy() if decision_surface_frame is not None else baseline_future
    download_frame = builder._build_download_frame(
        run_id=f"{run_id}-classifier-diagnostic",
        as_of_date=as_of_date,
        frame=source_frame,
    )
    review_input = _build_publish_review_input_frame(
        run_id=f"{run_id}-classifier-diagnostic",
        as_of_date=as_of_date,
        download_frame=download_frame,
    )
    review_frame = publisher._annotate_pos_eligibility(publisher._build_review_frame(review_input))
    labels = map_publishability_labels(review_frame)
    if decision_surface_frame is not None and "demand_evidence_class" in decision_surface_frame.columns:
        low_nonzero_mask = decision_surface_frame["demand_evidence_class"].fillna("").astype(str).str.strip().str.lower().eq("low_nonzero_demand")
    else:
        low_nonzero_mask = build_low_nonzero_mask(review_frame["forecast_promo_units"])
    classifier_rows = baseline_future.loc[low_nonzero_mask].copy()
    labels = labels.loc[low_nonzero_mask]
    if classifier_rows.empty or labels.dropna().empty:
        return LowNonzeroSpecialistClassifierDiagnostics(
            label_count=0,
            train_row_count=0,
            evaluation_row_count=0,
            macro_f1=None,
            accuracy=None,
            class_counts={},
            label_source="future_publishability_surface",
        )
    model_input, schema = build_specialist_model_input(classifier_rows, config=config)
    split_index = max(1, int(round(len(model_input.index) * 0.8)))
    train_features = model_input.iloc[:split_index]
    train_labels = labels.iloc[:split_index]
    evaluation_features = model_input.iloc[split_index:]
    evaluation_labels = labels.iloc[split_index:]
    if evaluation_features.empty:
        evaluation_features = train_features
        evaluation_labels = train_labels
    classifier = fit_multiclass_classifier_or_constant(
        schema,
        train_features,
        train_labels,
        config=config,
    )
    diagnostics = evaluate_multiclass_classifier(
        classifier,
        evaluation_features,
        evaluation_labels,
        label_source="future_publishability_surface",
    )
    return LowNonzeroSpecialistClassifierDiagnostics(
        label_count=diagnostics.label_count,
        train_row_count=int(len(train_features.index)),
        evaluation_row_count=diagnostics.evaluation_row_count,
        macro_f1=diagnostics.macro_f1,
        accuracy=diagnostics.accuracy,
        class_counts=diagnostics.class_counts,
        label_source=diagnostics.label_source,
    )


def _write_shadow_vs_baseline_diagnostics(
    *,
    run_id: str,
    as_of_date: str,
    output_root: Path,
    baseline_decision_surface_frame: pd.DataFrame,
    shadow_decision_surface_frame: pd.DataFrame,
    baseline_scored_frame: pd.DataFrame,
    shadow_scored_frame: pd.DataFrame,
    low_nonzero_gate_mask: pd.Series,
    scenario_summary_frame: pd.DataFrame,
) -> LowNonzeroShadowAttributionArtifacts:
    row_deltas = _build_shadow_vs_baseline_row_deltas(
        run_id=run_id,
        as_of_date=as_of_date,
        baseline_decision_surface_frame=baseline_decision_surface_frame,
        shadow_decision_surface_frame=shadow_decision_surface_frame,
        baseline_scored_frame=baseline_scored_frame,
        shadow_scored_frame=shadow_scored_frame,
        low_nonzero_gate_mask=low_nonzero_gate_mask,
    )
    reason_transitions = _build_shadow_vs_baseline_reason_transitions(row_deltas)
    threshold_blockers = _build_shadow_vs_baseline_threshold_blockers(row_deltas)
    summary = _build_shadow_vs_baseline_summary(
        run_id=run_id,
        as_of_date=as_of_date,
        row_deltas=row_deltas,
        reason_transitions=reason_transitions,
        threshold_blockers=threshold_blockers,
        scenario_summary_frame=scenario_summary_frame,
    )
    brief = _build_shadow_vs_baseline_brief(summary)

    row_deltas_csv_path = output_root / "shadow_vs_baseline_row_deltas.csv"
    reason_transitions_csv_path = output_root / "shadow_vs_baseline_reason_transitions.csv"
    threshold_blockers_csv_path = output_root / "shadow_vs_baseline_threshold_blockers.csv"
    summary_json_path = output_root / "shadow_vs_baseline_summary.json"
    brief_md_path = output_root / "shadow_vs_baseline_brief.md"

    row_deltas.to_csv(row_deltas_csv_path, index=False)
    reason_transitions.to_csv(reason_transitions_csv_path, index=False)
    threshold_blockers.to_csv(threshold_blockers_csv_path, index=False)
    write_json(summary_json_path, summary)
    brief_md_path.write_text(brief, encoding="utf-8")

    return LowNonzeroShadowAttributionArtifacts(
        row_deltas_csv_path=str(row_deltas_csv_path),
        reason_transitions_csv_path=str(reason_transitions_csv_path),
        threshold_blockers_csv_path=str(threshold_blockers_csv_path),
        summary_json_path=str(summary_json_path),
        brief_md_path=str(brief_md_path),
    )


def _build_shadow_vs_baseline_row_deltas(
    *,
    run_id: str,
    as_of_date: str,
    baseline_decision_surface_frame: pd.DataFrame,
    shadow_decision_surface_frame: pd.DataFrame,
    baseline_scored_frame: pd.DataFrame,
    shadow_scored_frame: pd.DataFrame,
    low_nonzero_gate_mask: pd.Series,
) -> pd.DataFrame:
    baseline_download, baseline_review = _build_publishability_diagnostic_frames(
        run_id=f"{run_id}-baseline-shadow-attribution",
        as_of_date=as_of_date,
        decision_surface_frame=baseline_decision_surface_frame,
    )
    shadow_download, shadow_review = _build_publishability_diagnostic_frames(
        run_id=f"{run_id}-gated-shadow-attribution",
        as_of_date=as_of_date,
        decision_surface_frame=shadow_decision_surface_frame,
    )
    return _assemble_shadow_vs_baseline_row_deltas(
        baseline_scored_alignment=_build_shadow_scored_alignment_frame(
            scored_frame=baseline_scored_frame,
            low_nonzero_gate_mask=low_nonzero_gate_mask,
        ),
        shadow_scored_alignment=_build_shadow_scored_alignment_frame(
            scored_frame=shadow_scored_frame,
            low_nonzero_gate_mask=low_nonzero_gate_mask,
        ),
        baseline_download_alignment=_build_shadow_download_alignment_frame(baseline_download),
        shadow_download_alignment=_build_shadow_download_alignment_frame(shadow_download),
        baseline_review_alignment=_build_shadow_review_alignment_frame(baseline_review),
        shadow_review_alignment=_build_shadow_review_alignment_frame(shadow_review),
    )


def _build_publishability_diagnostic_frames(
    *,
    run_id: str,
    as_of_date: str,
    decision_surface_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    builder = PromotionStorePredictionDownloadBuilder()
    publisher = StorePredictionPublisher()
    download_frame = builder._build_download_frame(
        run_id=run_id,
        as_of_date=as_of_date,
        frame=decision_surface_frame,
    )
    review_input = _build_publish_review_input_frame(
        run_id=run_id,
        as_of_date=as_of_date,
        download_frame=download_frame,
    )
    review_frame = publisher._annotate_pos_eligibility(
        publisher._build_review_frame(review_input)
    )
    return download_frame, review_frame


def _assemble_shadow_vs_baseline_row_deltas(
    *,
    baseline_scored_alignment: pd.DataFrame,
    shadow_scored_alignment: pd.DataFrame,
    baseline_download_alignment: pd.DataFrame,
    shadow_download_alignment: pd.DataFrame,
    baseline_review_alignment: pd.DataFrame,
    shadow_review_alignment: pd.DataFrame,
) -> pd.DataFrame:
    key_columns = list(SHADOW_JOIN_KEYS)
    row_deltas = _prefix_alignment_columns(
        baseline_download_alignment,
        prefix="baseline",
        key_columns=key_columns,
    ).merge(
        _prefix_alignment_columns(
            shadow_download_alignment,
            prefix="shadow",
            key_columns=key_columns,
        ),
        on=key_columns,
        how="outer",
    )
    row_deltas = row_deltas.merge(
        _prefix_alignment_columns(
            baseline_scored_alignment,
            prefix="baseline_raw",
            key_columns=key_columns,
        ),
        on=key_columns,
        how="left",
    ).merge(
        _prefix_alignment_columns(
            shadow_scored_alignment,
            prefix="shadow_raw",
            key_columns=key_columns,
        ),
        on=key_columns,
        how="left",
    )
    row_deltas = row_deltas.merge(
        _prefix_alignment_columns(
            baseline_review_alignment,
            prefix="baseline_review",
            key_columns=key_columns,
        ),
        on=key_columns,
        how="left",
    ).merge(
        _prefix_alignment_columns(
            shadow_review_alignment,
            prefix="shadow_review",
            key_columns=key_columns,
        ),
        on=key_columns,
        how="left",
    )

    for column_name in key_columns:
        row_deltas[column_name] = row_deltas[column_name].fillna("").astype(str)
    row_deltas["promotion_name"] = row_deltas["baseline_promotion_name"].where(
        row_deltas["baseline_promotion_name"].fillna("").astype(str).ne(""),
        row_deltas["shadow_promotion_name"],
    ).fillna("").astype(str)
    row_deltas["promo_type"] = row_deltas["baseline_promo_type"].where(
        row_deltas["baseline_promo_type"].fillna("").astype(str).ne(""),
        row_deltas["shadow_promo_type"],
    ).fillna("").astype(str)
    row_deltas["low_nonzero_gate_flag"] = row_deltas["baseline_raw_low_nonzero_gate_flag"].fillna(
        row_deltas["shadow_raw_low_nonzero_gate_flag"]
    ).fillna(False).astype(bool)

    numeric_delta_pairs = {
        "raw_predicted_units": ("baseline_raw_raw_predicted_units_sold", "shadow_raw_raw_predicted_units_sold"),
        "raw_model_confidence": (
            "baseline_raw_raw_row_model_confidence_score",
            "shadow_raw_raw_row_model_confidence_score",
        ),
        "predicted_units_total_promo": (
            "baseline_predicted_units_total_promo",
            "shadow_predicted_units_total_promo",
        ),
        "suggested_order_units": (
            "baseline_suggested_order_units",
            "shadow_suggested_order_units",
        ),
        "recommended_order_quantity": (
            "baseline_review_recommended_order_quantity",
            "shadow_review_recommended_order_quantity",
        ),
        "final_confidence_score": (
            "baseline_final_confidence_score",
            "shadow_final_confidence_score",
        ),
        "expected_incremental_value_dollars": (
            "baseline_expected_incremental_value_dollars",
            "shadow_expected_incremental_value_dollars",
        ),
        "risk_adjusted_value_of_speculative_units": (
            "baseline_risk_adjusted_value_of_speculative_units",
            "shadow_risk_adjusted_value_of_speculative_units",
        ),
    }
    for metric_name, (baseline_column, shadow_column) in numeric_delta_pairs.items():
        baseline_series = pd.to_numeric(row_deltas[baseline_column], errors="coerce")
        shadow_series = pd.to_numeric(row_deltas[shadow_column], errors="coerce")
        delta_name = f"{metric_name}_delta"
        row_deltas[delta_name] = shadow_series.fillna(0.0) - baseline_series.fillna(0.0)
        row_deltas[f"{metric_name}_delta_abs"] = row_deltas[delta_name].abs()

    text_delta_pairs = {
        "recommendation_reason": ("baseline_recommendation_reason", "shadow_recommendation_reason"),
        "demand_evidence_class": ("baseline_demand_evidence_class", "shadow_demand_evidence_class"),
        "decision_recommendation": ("baseline_decision_recommendation", "shadow_decision_recommendation"),
        "publish_bucket": ("baseline_review_publish_bucket", "shadow_review_publish_bucket"),
        "publish_reason": ("baseline_review_publish_reason", "shadow_review_publish_reason"),
        "review_reason": ("baseline_review_review_reason", "shadow_review_review_reason"),
        "exclusion_reason": ("baseline_review_exclusion_reason", "shadow_review_exclusion_reason"),
        "decision_action": ("baseline_review_decision_action", "shadow_review_decision_action"),
        "trust_floor_status": ("baseline_trust_floor_status", "shadow_trust_floor_status"),
    }
    for metric_name, (baseline_column, shadow_column) in text_delta_pairs.items():
        baseline_series = row_deltas[baseline_column].fillna("").astype(str)
        shadow_series = row_deltas[shadow_column].fillna("").astype(str)
        row_deltas[f"{metric_name}_changed_flag"] = baseline_series.ne(shadow_series)
        row_deltas[f"baseline_{metric_name}"] = baseline_series
        row_deltas[f"shadow_{metric_name}"] = shadow_series

    row_deltas["baseline_cold_start_flag"] = row_deltas["baseline_cold_start_flag"].fillna(False).astype(bool)
    row_deltas["shadow_cold_start_flag"] = row_deltas["shadow_cold_start_flag"].fillna(False).astype(bool)
    row_deltas["baseline_insufficient_history_flag"] = row_deltas["baseline_insufficient_history_flag"].fillna(False).astype(bool)
    row_deltas["shadow_insufficient_history_flag"] = row_deltas["shadow_insufficient_history_flag"].fillna(False).astype(bool)
    row_deltas["baseline_stock_gap_flag"] = row_deltas["baseline_stock_gap_flag"].fillna(False).astype(bool)
    row_deltas["shadow_stock_gap_flag"] = row_deltas["shadow_stock_gap_flag"].fillna(False).astype(bool)
    row_deltas["baseline_trust_floor_risk_flag"] = row_deltas["baseline_trust_floor_risk_flag"].fillna(False).astype(bool)
    row_deltas["shadow_trust_floor_risk_flag"] = row_deltas["shadow_trust_floor_risk_flag"].fillna(False).astype(bool)

    row_deltas["sparse_history_flag"] = (
        row_deltas["baseline_cold_start_flag"]
        | row_deltas["shadow_cold_start_flag"]
        | row_deltas["baseline_insufficient_history_flag"]
        | row_deltas["shadow_insufficient_history_flag"]
        | row_deltas["baseline_demand_evidence_class"].str.strip().str.lower().isin(SPARSE_HISTORY_DEMAND_CLASSES)
        | row_deltas["shadow_demand_evidence_class"].str.strip().str.lower().isin(SPARSE_HISTORY_DEMAND_CLASSES)
    )
    row_deltas["stock_gap_flag"] = row_deltas["baseline_stock_gap_flag"] | row_deltas["shadow_stock_gap_flag"]
    row_deltas["trust_floor_risk_flag"] = (
        row_deltas["baseline_trust_floor_risk_flag"] | row_deltas["shadow_trust_floor_risk_flag"]
    )
    row_deltas["material_shadow_delta_flag"] = (
        row_deltas["raw_predicted_units_delta_abs"].ge(MATERIAL_RAW_PREDICTED_UNITS_DELTA_MIN)
        | row_deltas["raw_model_confidence_delta_abs"].ge(MATERIAL_RAW_CONFIDENCE_DELTA_MIN)
    )
    row_deltas["commercial_signal_changed_flag"] = (
        row_deltas["predicted_units_total_promo_delta_abs"].gt(0.0)
        | row_deltas["suggested_order_units_delta_abs"].gt(0.0)
        | row_deltas["expected_incremental_value_dollars_delta_abs"].gt(0.0)
        | row_deltas["final_confidence_score_delta_abs"].gt(0.0)
    )
    row_deltas["active_blocker_count"] = (
        row_deltas["stock_gap_flag"].astype(int)
        + row_deltas["trust_floor_risk_flag"].astype(int)
        + row_deltas["sparse_history_flag"].astype(int)
        + row_deltas["shadow_publish_bucket"].ne("publish_eligible").astype(int)
    )
    row_deltas["publish_flip_gap_score"] = _resolve_publish_flip_gap_score(row_deltas)

    blocker_categories: list[str] = []
    blocker_mechanisms: list[str] = []
    remained_excluded_flags: list[bool] = []
    remained_review_flags: list[bool] = []
    for row in row_deltas.itertuples(index=False):
        row_changed_publishability = bool(
            row.publish_bucket_changed_flag
            or row.publish_reason_changed_flag
            or row.review_reason_changed_flag
            or row.exclusion_reason_changed_flag
            or row.decision_action_changed_flag
        )
        raw_changed = bool(row.material_shadow_delta_flag)
        commercial_changed = bool(row.commercial_signal_changed_flag)
        stock_gap_flag = bool(row.stock_gap_flag)
        trust_floor_flag = bool(row.trust_floor_risk_flag)
        sparse_history_flag = bool(row.sparse_history_flag)
        threshold_limited = bool(
            abs(float(row.predicted_units_total_promo_delta or 0.0)) < COMMERCIAL_THRESHOLD_UNIT_DELTA_MIN
            and abs(float(row.suggested_order_units_delta or 0.0)) < COMMERCIAL_THRESHOLD_UNIT_DELTA_MIN
            and abs(float(row.expected_incremental_value_dollars_delta or 0.0)) < COMMERCIAL_THRESHOLD_VALUE_DELTA_MIN
            and abs(float(row.final_confidence_score_delta or 0.0)) < COMMERCIAL_THRESHOLD_CONFIDENCE_DELTA_MIN
        )

        if row_changed_publishability:
            blocker_category = "policy_effect_realized"
            blocker_mechanism = "publishability_transition_materialized"
        elif raw_changed and not commercial_changed:
            blocker_category = "model_improvement_with_no_policy_effect"
            blocker_mechanism = "commercial_forecast_source_priority_override"
        elif commercial_changed and (stock_gap_flag or trust_floor_flag):
            blocker_category = "improvement_blocked_by_stock_gap_trust_floor_policy"
            if stock_gap_flag and trust_floor_flag:
                blocker_mechanism = "stock_gap_and_trust_floor_policy"
            elif stock_gap_flag:
                blocker_mechanism = "stock_gap_policy"
            else:
                blocker_mechanism = "trust_floor_policy"
        elif commercial_changed and sparse_history_flag:
            blocker_category = "improvement_blocked_by_sparse_history_evidence_gates"
            if bool(row.shadow_cold_start_flag) or bool(row.baseline_cold_start_flag):
                blocker_mechanism = "cold_start_evidence_gate"
            elif bool(row.shadow_insufficient_history_flag) or bool(row.baseline_insufficient_history_flag):
                blocker_mechanism = "insufficient_history_evidence_gate"
            else:
                blocker_mechanism = "sparse_history_demand_evidence_gate"
        elif commercial_changed and threshold_limited:
            blocker_category = "improvement_too_small_to_cross_action_thresholds"
            blocker_mechanism = "sub_integer_or_same_action_threshold"
        elif commercial_changed:
            blocker_category = "improvement_offset_by_other_downstream_features"
            blocker_mechanism = "downstream_value_and_reason_offsets"
        elif raw_changed:
            blocker_category = "model_improvement_with_no_policy_effect"
            blocker_mechanism = "shadow_signal_not_propagated"
        else:
            blocker_category = "no_material_shadow_change"
            blocker_mechanism = "no_material_delta"

        remained_excluded = bool(
            raw_changed
            and str(row.baseline_publish_bucket) == "excluded_legitimate"
            and str(row.shadow_publish_bucket) == "excluded_legitimate"
        )
        remained_review = bool(
            raw_changed
            and str(row.baseline_publish_bucket) == "review_only"
            and str(row.shadow_publish_bucket) == "review_only"
        )
        blocker_categories.append(blocker_category)
        blocker_mechanisms.append(blocker_mechanism)
        remained_excluded_flags.append(remained_excluded)
        remained_review_flags.append(remained_review)

    row_deltas["blocker_category"] = blocker_categories
    row_deltas["blocker_mechanism"] = blocker_mechanisms
    row_deltas["material_shadow_change_but_remained_excluded_flag"] = remained_excluded_flags
    row_deltas["material_shadow_change_but_remained_review_only_flag"] = remained_review_flags
    return row_deltas.sort_values(list(SHADOW_JOIN_KEYS), kind="mergesort").reset_index(drop=True)


def _build_shadow_scored_alignment_frame(
    *,
    scored_frame: pd.DataFrame,
    low_nonzero_gate_mask: pd.Series,
) -> pd.DataFrame:
    source = _prepare_feature_inspection_source_frame(scored_frame)
    if source is None or source.empty:
        return pd.DataFrame(columns=[*SHADOW_JOIN_KEYS, "promotion_row_key", "raw_predicted_units_sold", "raw_row_model_confidence_score", "low_nonzero_gate_flag"])
    work = source.loc[:, list(SHADOW_JOIN_KEYS)].copy()
    work["promotion_row_key"] = _text_frame_series(source, ("promotion_row_key",), default="")
    work["raw_predicted_units_sold"] = _numeric_frame_series(scored_frame, ("predicted_units_sold",), default=0.0)
    work["raw_row_model_confidence_score"] = _numeric_frame_series(scored_frame, ("row_model_confidence_score",), default=0.0)
    work["low_nonzero_gate_flag"] = low_nonzero_gate_mask.reindex(scored_frame.index, fill_value=False).astype(bool)
    return _collapse_shadow_alignment_frame(work)


def _build_shadow_download_alignment_frame(download_frame: pd.DataFrame) -> pd.DataFrame:
    if download_frame.empty:
        return pd.DataFrame(columns=[*SHADOW_JOIN_KEYS])
    expected_incremental_value = _resolve_expected_incremental_value_series(download_frame)
    projected_stock_gap_units = _numeric_frame_series(
        download_frame,
        ("projected_stock_gap_units", "suggested_order_units"),
        default=0.0,
    ).fillna(0.0)
    trust_floor_status = _text_frame_series(download_frame, ("trust_floor_status",), default="")
    cold_start_flag = _bool_numeric_series(download_frame, ("cold_start_flag",))
    insufficient_history_flag = _bool_numeric_series(download_frame, ("insufficient_history_flag",))
    demand_evidence_class = _text_frame_series(download_frame, ("demand_evidence_class",), default="")
    alignment = pd.DataFrame(
        {
            "store_number": _text_frame_series(download_frame, ("store_number",), default=""),
            "promotion_header_key": _text_frame_series(download_frame, ("promotion_header_key",), default=""),
            "sku_number": _text_frame_series(download_frame, ("sku_number",), default=""),
            "promotion_name": _text_frame_series(download_frame, ("promotion_name",), default=""),
            "promo_type": _text_frame_series(download_frame, ("promo_type",), default=""),
            "recommendation_reason": _text_frame_series(download_frame, ("decision_reason", "client_reason"), default=""),
            "predicted_units_total_promo": _numeric_frame_series(download_frame, ("predicted_units_total_promo",), default=0.0),
            "predicted_units_until_promo_start": _numeric_frame_series(download_frame, ("predicted_units_until_promo_start",), default=0.0),
            "current_soh_units": _numeric_frame_series(download_frame, ("current_soh_units",), default=0.0),
            "qty_on_order_units": _numeric_frame_series(download_frame, ("qty_on_order_units", "on_order_units"), default=0.0),
            "suggested_order_units": _numeric_frame_series(download_frame, ("suggested_order_units",), default=0.0),
            "final_confidence_score": _numeric_frame_series(download_frame, ("final_confidence_score",), default=0.0),
            "expected_incremental_value_dollars": expected_incremental_value,
            "risk_adjusted_value_of_speculative_units": _numeric_frame_series(
                download_frame,
                ("risk_adjusted_value_of_speculative_units",),
                default=0.0,
            ),
            "trust_floor_status": trust_floor_status,
            "projected_stock_gap_units": projected_stock_gap_units,
            "stock_gap_flag": projected_stock_gap_units.gt(0.0),
            "trust_floor_risk_flag": trust_floor_status.fillna("").astype(str).str.strip().str.lower().ne("")
            & trust_floor_status.fillna("").astype(str).str.strip().str.lower().ne("trust_floor_met"),
            "decision_recommendation": _text_frame_series(download_frame, ("decision_recommendation",), default=""),
            "demand_evidence_class": demand_evidence_class,
            "cold_start_flag": cold_start_flag,
            "insufficient_history_flag": insufficient_history_flag,
        }
    )
    return _collapse_shadow_alignment_frame(alignment)


def _build_shadow_review_alignment_frame(review_frame: pd.DataFrame) -> pd.DataFrame:
    if review_frame.empty:
        return pd.DataFrame(columns=[*SHADOW_JOIN_KEYS])
    alignment = pd.DataFrame(
        {
            "store_number": _text_frame_series(review_frame, ("store_number",), default=""),
            "promotion_header_key": _text_frame_series(review_frame, ("promotion_id",), default=""),
            "sku_number": _text_frame_series(review_frame, ("sku_number",), default=""),
            "recommended_order_quantity": _numeric_frame_series(review_frame, ("recommended_order_quantity",), default=0.0),
            "confidence_score": _numeric_frame_series(review_frame, ("confidence_score",), default=0.0),
            "publish_bucket": _text_frame_series(review_frame, ("publish_eligibility_class",), default=""),
            "publish_reason": _text_frame_series(review_frame, ("publish_eligibility_reason",), default=""),
            "review_reason": _text_frame_series(review_frame, ("review_reason",), default=""),
            "exclusion_reason": _text_frame_series(
                review_frame,
                ("excluded_from_publish_reason", "exclusion_reason_primary"),
                default="",
            ),
            "decision_action": _text_frame_series(review_frame, ("decision_action",), default=""),
        }
    )
    return _collapse_shadow_alignment_frame(alignment)


def _build_shadow_vs_baseline_reason_transitions(row_deltas: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    transition_specs = (
        ("publish_bucket", "baseline_publish_bucket", "shadow_publish_bucket"),
        ("publish_reason", "baseline_publish_reason", "shadow_publish_reason"),
        ("review_reason", "baseline_review_reason", "shadow_review_reason"),
        ("exclusion_reason", "baseline_exclusion_reason", "shadow_exclusion_reason"),
        ("decision_action", "baseline_decision_action", "shadow_decision_action"),
    )
    group_dimensions = {"all": None, **SHADOW_GROUP_DIMENSIONS}
    for group_dimension, column_name in group_dimensions.items():
        work = row_deltas.copy()
        if column_name is None:
            work["group_value"] = "all"
        else:
            work["group_value"] = work[column_name].fillna("unknown").astype(str)
        for transition_type, baseline_column, shadow_column in transition_specs:
            grouped = work.groupby(["group_value", baseline_column, shadow_column], dropna=False)
            for (group_value, baseline_value, shadow_value), group in grouped:
                rows.append(
                    {
                        "group_dimension": group_dimension,
                        "group_value": str(group_value),
                        "transition_type": transition_type,
                        "baseline_value": str(baseline_value),
                        "shadow_value": str(shadow_value),
                        "row_count": int(len(group.index)),
                        "material_shadow_delta_row_count": int(group["material_shadow_delta_flag"].sum()),
                        "commercial_signal_changed_row_count": int(group["commercial_signal_changed_flag"].sum()),
                        "publish_bucket_changed_row_count": int(group["publish_bucket_changed_flag"].sum()),
                        "avg_raw_predicted_units_delta": _maybe_float(group["raw_predicted_units_delta"].mean()),
                        "avg_commercial_predicted_units_delta": _maybe_float(group["predicted_units_total_promo_delta"].mean()),
                        "avg_expected_incremental_value_delta": _maybe_float(group["expected_incremental_value_dollars_delta"].mean()),
                    }
                )
    return pd.DataFrame(rows)


def _build_shadow_vs_baseline_threshold_blockers(row_deltas: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_dimensions = {"all": None, **SHADOW_GROUP_DIMENSIONS}
    for group_dimension, column_name in group_dimensions.items():
        work = row_deltas.copy()
        if column_name is None:
            work["group_value"] = "all"
        else:
            work["group_value"] = work[column_name].fillna("unknown").astype(str)
        grouped = work.groupby(["group_value", "blocker_category", "blocker_mechanism"], dropna=False)
        for (group_value, blocker_category, blocker_mechanism), group in grouped:
            rows.append(
                {
                    "group_dimension": group_dimension,
                    "group_value": str(group_value),
                    "blocker_category": str(blocker_category),
                    "blocker_mechanism": str(blocker_mechanism),
                    "row_count": int(len(group.index)),
                    "material_shadow_delta_row_count": int(group["material_shadow_delta_flag"].sum()),
                    "commercial_signal_changed_row_count": int(group["commercial_signal_changed_flag"].sum()),
                    "publish_bucket_changed_row_count": int(group["publish_bucket_changed_flag"].sum()),
                    "remained_excluded_row_count": int(group["material_shadow_change_but_remained_excluded_flag"].sum()),
                    "remained_review_only_row_count": int(group["material_shadow_change_but_remained_review_only_flag"].sum()),
                    "avg_raw_predicted_units_delta_abs": _maybe_float(group["raw_predicted_units_delta_abs"].mean()),
                    "avg_commercial_predicted_units_delta_abs": _maybe_float(group["predicted_units_total_promo_delta_abs"].mean()),
                    "avg_expected_incremental_value_delta": _maybe_float(group["expected_incremental_value_dollars_delta"].mean()),
                    "avg_confidence_delta": _maybe_float(group["final_confidence_score_delta"].mean()),
                }
            )
    threshold_blockers = pd.DataFrame(rows)
    if threshold_blockers.empty:
        return threshold_blockers
    threshold_blockers["global_blocker_rank"] = pd.NA
    global_mask = threshold_blockers["group_dimension"].eq("all")
    global_order = threshold_blockers.loc[global_mask].sort_values(
        by=["material_shadow_delta_row_count", "row_count", "avg_raw_predicted_units_delta_abs"],
        ascending=[False, False, False],
        kind="mergesort",
    )
    if not global_order.empty:
        threshold_blockers.loc[global_order.index, "global_blocker_rank"] = range(1, len(global_order.index) + 1)
    return threshold_blockers


def _build_shadow_vs_baseline_summary(
    *,
    run_id: str,
    as_of_date: str,
    row_deltas: pd.DataFrame,
    reason_transitions: pd.DataFrame,
    threshold_blockers: pd.DataFrame,
    scenario_summary_frame: pd.DataFrame,
) -> dict[str, object]:
    baseline_publish_count = int(row_deltas["baseline_publish_bucket"].eq("publish_eligible").sum())
    shadow_publish_count = int(row_deltas["shadow_publish_bucket"].eq("publish_eligible").sum())
    baseline_review_count = int(row_deltas["baseline_publish_bucket"].eq("review_only").sum())
    shadow_review_count = int(row_deltas["shadow_publish_bucket"].eq("review_only").sum())
    baseline_excluded_count = int(row_deltas["baseline_publish_bucket"].eq("excluded_legitimate").sum())
    shadow_excluded_count = int(row_deltas["shadow_publish_bucket"].eq("excluded_legitimate").sum())
    top_blockers = threshold_blockers.loc[threshold_blockers["group_dimension"].eq("all")].sort_values(
        by=["material_shadow_delta_row_count", "row_count", "avg_raw_predicted_units_delta_abs"],
        ascending=[False, False, False],
        kind="mergesort",
    ).head(10)
    publish_bucket_transitions = reason_transitions.loc[
        reason_transitions["group_dimension"].eq("all")
        & reason_transitions["transition_type"].eq("publish_bucket")
    ].sort_values(by=["row_count", "material_shadow_delta_row_count"], ascending=[False, False], kind="mergesort").head(10)
    baseline_scenario = scenario_summary_frame.loc[
        scenario_summary_frame["scenario_id"].eq(SCENARIO_CURRENT_SLIM)
    ].iloc[0]
    shadow_scenario = scenario_summary_frame.loc[
        scenario_summary_frame["scenario_id"].eq(SCENARIO_GATED)
    ].iloc[0]

    summary = {
        "run_id": run_id,
        "as_of_date": as_of_date,
        "row_count": int(len(row_deltas.index)),
        "low_nonzero_gate_row_count": int(row_deltas["low_nonzero_gate_flag"].sum()),
        "raw_model_changed_row_count": int(row_deltas["material_shadow_delta_flag"].sum()),
        "commercial_predicted_units_changed_row_count": int(row_deltas["predicted_units_total_promo_delta_abs"].gt(0.0).sum()),
        "expected_incremental_value_changed_row_count": int(
            row_deltas["expected_incremental_value_dollars_delta_abs"].gt(0.0).sum()
        ),
        "final_confidence_changed_row_count": int(row_deltas["final_confidence_score_delta_abs"].gt(0.0).sum()),
        "publish_bucket_changed_row_count": int(row_deltas["publish_bucket_changed_flag"].sum()),
        "publish_reason_changed_row_count": int(row_deltas["publish_reason_changed_flag"].sum()),
        "review_reason_changed_row_count": int(row_deltas["review_reason_changed_flag"].sum()),
        "exclusion_reason_changed_row_count": int(row_deltas["exclusion_reason_changed_flag"].sum()),
        "decision_action_changed_row_count": int(row_deltas["decision_action_changed_flag"].sum()),
        "baseline_publish_eligible_row_count": baseline_publish_count,
        "shadow_publish_eligible_row_count": shadow_publish_count,
        "baseline_review_only_row_count": baseline_review_count,
        "shadow_review_only_row_count": shadow_review_count,
        "baseline_excluded_legitimate_row_count": baseline_excluded_count,
        "shadow_excluded_legitimate_row_count": shadow_excluded_count,
        "publish_eligible_delta": shadow_publish_count - baseline_publish_count,
        "review_only_delta": shadow_review_count - baseline_review_count,
        "excluded_legitimate_delta": shadow_excluded_count - baseline_excluded_count,
        "no_policy_change_flag": bool(
            int(row_deltas["publish_bucket_changed_flag"].sum()) == 0
            and int(row_deltas["publish_reason_changed_flag"].sum()) == 0
            and int(row_deltas["review_reason_changed_flag"].sum()) == 0
            and int(row_deltas["exclusion_reason_changed_flag"].sum()) == 0
            and int(row_deltas["decision_action_changed_flag"].sum()) == 0
        ),
        "publishability_widening_detected_flag": bool(shadow_publish_count > baseline_publish_count),
        "blocker_category_counts": {
            str(key): int(value)
            for key, value in row_deltas["blocker_category"].astype(str).value_counts(dropna=False).to_dict().items()
        },
        "baseline_publish_bucket_counts": {
            str(key): int(value)
            for key, value in row_deltas["baseline_publish_bucket"].astype(str).value_counts(dropna=False).to_dict().items()
        },
        "shadow_publish_bucket_counts": {
            str(key): int(value)
            for key, value in row_deltas["shadow_publish_bucket"].astype(str).value_counts(dropna=False).to_dict().items()
        },
        "top_10_blocker_mechanisms": top_blockers.to_dict(orient="records"),
        "publish_bucket_transition_highlights": publish_bucket_transitions.to_dict(orient="records"),
        "rows_with_material_shadow_change_but_remaining_excluded": _interesting_shadow_rows(
            row_deltas.loc[row_deltas["material_shadow_change_but_remained_excluded_flag"]].copy(),
            limit=25,
        ),
        "rows_with_material_shadow_change_but_remaining_review_only": _interesting_shadow_rows(
            row_deltas.loc[row_deltas["material_shadow_change_but_remained_review_only_flag"]].copy(),
            limit=25,
        ),
        "rows_closest_to_flipping_to_publishable": _interesting_shadow_rows(
            row_deltas.loc[row_deltas["shadow_publish_bucket"].ne("publish_eligible")].copy(),
            limit=25,
            sort_columns=["publish_flip_gap_score", "active_blocker_count", "raw_predicted_units_delta_abs"],
            ascending=[True, True, False],
        ),
        "grouped_blocker_highlights": {
            group_dimension: threshold_blockers.loc[
                threshold_blockers["group_dimension"].eq(group_dimension)
            ].sort_values(
                by=["material_shadow_delta_row_count", "row_count"],
                ascending=[False, False],
                kind="mergesort",
            ).head(5).to_dict(orient="records")
            for group_dimension in SHADOW_GROUP_DIMENSIONS
        },
        "baseline_metrics": {
            "mae": _maybe_float(baseline_scenario.get("mae")),
            "mape": _maybe_float(baseline_scenario.get("mape")),
            "overforecast_rate": _maybe_float(baseline_scenario.get("overforecast_rate")),
        },
        "shadow_metrics": {
            "mae": _maybe_float(shadow_scenario.get("mae")),
            "mape": _maybe_float(shadow_scenario.get("mape")),
            "overforecast_rate": _maybe_float(shadow_scenario.get("overforecast_rate")),
        },
    }
    recommendation, rationale = _resolve_shadow_recommendation(summary)
    summary["recommendation"] = recommendation
    summary["recommendation_rationale"] = rationale
    return summary


def _build_shadow_vs_baseline_brief(summary: dict[str, object]) -> str:
    top_blockers = list(summary.get("top_10_blocker_mechanisms", []))
    top_blocker_line = "- Top blocker: `none`"
    if top_blockers:
        top_blocker = top_blockers[0]
        top_blocker_line = (
            f"- Top blocker: `{top_blocker.get('blocker_mechanism')}` on "
            f"`{top_blocker.get('material_shadow_delta_row_count')}` materially changed rows"
        )
    lines = [
        f"# Shadow vs Baseline Attribution: {summary['run_id']}",
        "",
        "## Calibration vs Publishability",
        f"- Baseline MAE / overforecast: `{summary['baseline_metrics']['mae']}` / `{summary['baseline_metrics']['overforecast_rate']}`",
        f"- Gated shadow MAE / overforecast: `{summary['shadow_metrics']['mae']}` / `{summary['shadow_metrics']['overforecast_rate']}`",
        f"- Raw specialist-shadow rows with material model movement: `{summary['raw_model_changed_row_count']}`",
        f"- Commercial predicted-units rows changed after Stage 11: `{summary['commercial_predicted_units_changed_row_count']}`",
        f"- Expected incremental value rows changed: `{summary['expected_incremental_value_changed_row_count']}`",
        f"- Final confidence rows changed: `{summary['final_confidence_changed_row_count']}`",
        f"- Publish bucket rows changed after Stage 12: `{summary['publish_bucket_changed_row_count']}`",
        "",
        "## Neutralization Diagnosis",
        top_blocker_line,
        f"- Material shadow change but still excluded: `{len(summary['rows_with_material_shadow_change_but_remaining_excluded'])}` rows surfaced in the summary JSON.",
        f"- Material shadow change but still review-only: `{len(summary['rows_with_material_shadow_change_but_remaining_review_only'])}` rows surfaced in the summary JSON.",
        f"- Publish-eligible delta: `{summary['publish_eligible_delta']}`; review-only delta: `{summary['review_only_delta']}`; excluded delta: `{summary['excluded_legitimate_delta']}`",
        "",
        "## Recommendation",
        f"- Recommendation: `{summary['recommendation']}`",
        f"- Rationale: {summary['recommendation_rationale']}",
    ]
    return "\n".join(lines) + "\n"


def _resolve_shadow_recommendation(summary: dict[str, object]) -> tuple[str, str]:
    raw_changed = int(summary.get("raw_model_changed_row_count", 0))
    commercial_changed = int(summary.get("commercial_predicted_units_changed_row_count", 0))
    value_changed = int(summary.get("expected_incremental_value_changed_row_count", 0))
    confidence_changed = int(summary.get("final_confidence_changed_row_count", 0))
    publish_changed = int(summary.get("publish_bucket_changed_row_count", 0))

    if raw_changed > 0 and commercial_changed == 0 and value_changed == 0 and publish_changed == 0:
        return (
            "route specialist into downstream value calculation seam",
            "The specialist materially changes raw low-nonzero forecasts, but none of that signal reaches Stage 11 predicted units, value, confidence, or Stage 12 publish buckets. The smallest governed seam where the information can matter next is the downstream value calculation path, not BUY/ORDER policy.",
        )
    if value_changed > 0 and publish_changed == 0:
        return (
            "route specialist into downstream value calculation seam",
            "The specialist reaches commercial value metrics without changing publish buckets. The next safe seam is to use the signal in downstream value calculations while keeping BUY/ORDER and Stage 12 policy unchanged.",
        )
    if confidence_changed > 0 and publish_changed == 0:
        return (
            "route specialist into confidence/review triage only",
            "The specialist changes confidence more than economic outputs, so the smallest safe operational seam is review triage rather than value or quantity logic.",
        )
    if raw_changed > 0 and publish_changed == 0:
        return (
            "keep specialist as shadow-calibration only",
            "The specialist improves calibration diagnostics but does not produce a governed downstream effect on the current future commercial surface.",
        )
    return (
        "reject operationalization for now",
        "The attribution pass did not show a stable governed seam where the specialist signal produces useful downstream movement without changing policy behaviour.",
    )


def _write_specialist_value_shadow_diagnostics(
    *,
    run_id: str,
    as_of_date: str,
    output_root: Path,
    baseline_decision_surface_frame: pd.DataFrame,
    baseline_scored_frame: pd.DataFrame,
    shadow_scored_frame: pd.DataFrame,
    low_nonzero_gate_mask: pd.Series,
    scenario_summary_frame: pd.DataFrame,
) -> LowNonzeroValueShadowArtifacts:
    row_deltas = _build_specialist_value_shadow_row_deltas(
        run_id=run_id,
        as_of_date=as_of_date,
        baseline_decision_surface_frame=baseline_decision_surface_frame,
        baseline_scored_frame=baseline_scored_frame,
        shadow_scored_frame=shadow_scored_frame,
        low_nonzero_gate_mask=low_nonzero_gate_mask,
    )
    reason_transitions = _build_specialist_value_shadow_reason_transitions(row_deltas)
    flip_candidates = _build_specialist_value_shadow_flip_candidates(row_deltas)
    summary = _build_specialist_value_shadow_summary(
        run_id=run_id,
        as_of_date=as_of_date,
        row_deltas=row_deltas,
        reason_transitions=reason_transitions,
        flip_candidates=flip_candidates,
        scenario_summary_frame=scenario_summary_frame,
    )
    brief = _build_specialist_value_shadow_brief(summary)

    row_deltas_csv_path = output_root / "specialist_value_shadow_row_deltas.csv"
    reason_transitions_csv_path = output_root / "specialist_value_shadow_reason_transitions.csv"
    summary_json_path = output_root / "specialist_value_shadow_summary.json"
    brief_md_path = output_root / "specialist_value_shadow_brief.md"
    flip_candidates_csv_path = output_root / "specialist_value_shadow_flip_candidates.csv"

    row_deltas.to_csv(row_deltas_csv_path, index=False)
    reason_transitions.to_csv(reason_transitions_csv_path, index=False)
    flip_candidates.to_csv(flip_candidates_csv_path, index=False)
    write_json(summary_json_path, summary)
    brief_md_path.write_text(brief, encoding="utf-8")
    return LowNonzeroValueShadowArtifacts(
        row_deltas_csv_path=str(row_deltas_csv_path),
        reason_transitions_csv_path=str(reason_transitions_csv_path),
        summary_json_path=str(summary_json_path),
        brief_md_path=str(brief_md_path),
        flip_candidates_csv_path=str(flip_candidates_csv_path),
    )


def _build_specialist_value_shadow_row_deltas(
    *,
    run_id: str,
    as_of_date: str,
    baseline_decision_surface_frame: pd.DataFrame,
    baseline_scored_frame: pd.DataFrame,
    shadow_scored_frame: pd.DataFrame,
    low_nonzero_gate_mask: pd.Series,
) -> pd.DataFrame:
    baseline_download, baseline_review = _build_publishability_diagnostic_frames(
        run_id=f"{run_id}-value-shadow-baseline",
        as_of_date=as_of_date,
        decision_surface_frame=baseline_decision_surface_frame,
    )
    baseline_download_alignment = _build_shadow_download_alignment_frame(baseline_download)
    baseline_review_alignment = _build_shadow_review_alignment_frame(baseline_review)
    baseline_scored_alignment = _build_shadow_scored_alignment_frame(
        scored_frame=baseline_scored_frame,
        low_nonzero_gate_mask=low_nonzero_gate_mask,
    )
    shadow_scored_alignment = _build_shadow_scored_alignment_frame(
        scored_frame=shadow_scored_frame,
        low_nonzero_gate_mask=low_nonzero_gate_mask,
    )
    source_alignment = _build_value_shadow_source_alignment_frame(baseline_decision_surface_frame)

    key_columns = list(SHADOW_JOIN_KEYS)
    row_deltas = baseline_download_alignment.merge(
        baseline_review_alignment,
        on=key_columns,
        how="left",
        suffixes=("", "_review"),
    ).merge(
        _prefix_alignment_columns(
            baseline_scored_alignment,
            prefix="baseline_raw",
            key_columns=key_columns,
        ),
        on=key_columns,
        how="left",
    ).merge(
        _prefix_alignment_columns(
            shadow_scored_alignment,
            prefix="shadow_raw",
            key_columns=key_columns,
        ),
        on=key_columns,
        how="left",
    ).merge(
        source_alignment,
        on=key_columns,
        how="left",
    )
    for column_name in key_columns:
        row_deltas[column_name] = row_deltas[column_name].fillna("").astype(str)

    baseline_commercial_forecast = pd.to_numeric(row_deltas["predicted_units_total_promo"], errors="coerce").fillna(0.0).clip(lower=0.0)
    baseline_expected_incremental_units = pd.to_numeric(
        row_deltas["source_expected_incremental_units"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    shadow_raw_units = pd.to_numeric(row_deltas["shadow_raw_raw_predicted_units_sold"], errors="coerce").fillna(0.0).clip(lower=0.0)
    gate_flag = row_deltas["baseline_raw_low_nonzero_gate_flag"].fillna(
        row_deltas["shadow_raw_low_nonzero_gate_flag"],
    ).fillna(False).astype(bool)
    shadow_specialist_supported_units = pd.concat(
        [baseline_commercial_forecast, shadow_raw_units],
        axis=1,
    ).min(axis=1).where(gate_flag, baseline_expected_incremental_units).clip(lower=0.0)

    baseline_value_metrics = _build_value_shadow_metric_frame(
        row_frame=row_deltas,
        expected_total_units=baseline_commercial_forecast,
        expected_incremental_units=baseline_expected_incremental_units,
    )
    shadow_value_metrics = _build_value_shadow_metric_frame(
        row_frame=row_deltas,
        expected_total_units=baseline_commercial_forecast,
        expected_incremental_units=shadow_specialist_supported_units,
    )
    for column_name in baseline_value_metrics.columns:
        row_deltas[f"baseline_value_{column_name}"] = baseline_value_metrics[column_name]
        row_deltas[f"shadow_value_{column_name}"] = shadow_value_metrics[column_name]
        if pd.api.types.is_numeric_dtype(baseline_value_metrics[column_name]):
            row_deltas[f"{column_name}_delta"] = (
                pd.to_numeric(shadow_value_metrics[column_name], errors="coerce").fillna(0.0)
                - pd.to_numeric(baseline_value_metrics[column_name], errors="coerce").fillna(0.0)
            )

    baseline_publish_reason = row_deltas["publish_reason"].fillna("").astype(str)
    baseline_review_reason = row_deltas["review_reason"].fillna("").astype(str)
    baseline_decision_action = row_deltas["decision_action"].fillna("").astype(str).str.upper()
    row_deltas["low_nonzero_gate_flag"] = gate_flag
    row_deltas["cold_start_flag"] = row_deltas["cold_start_flag"].fillna(False).astype(bool)
    row_deltas["insufficient_history_flag"] = row_deltas["insufficient_history_flag"].fillna(False).astype(bool)
    row_deltas["stock_gap_flag"] = row_deltas["stock_gap_flag"].fillna(False).astype(bool)
    row_deltas["trust_floor_risk_flag"] = row_deltas["trust_floor_risk_flag"].fillna(False).astype(bool)
    row_deltas["sparse_history_flag"] = (
        row_deltas["cold_start_flag"]
        | row_deltas["insufficient_history_flag"]
        | row_deltas["demand_evidence_class"].fillna("").astype(str).str.strip().str.lower().isin(SPARSE_HISTORY_DEMAND_CLASSES)
    )
    row_deltas["forecast_source_priority_changed_flag"] = False
    row_deltas["commercial_predicted_units_changed_flag"] = False
    row_deltas["stage12_publish_bucket_changed_flag"] = False
    row_deltas["buy_order_widening_flag"] = False
    row_deltas["stage12_publishability_widening_flag"] = False
    row_deltas["non_gated_value_delta_leak_flag"] = (
        ~gate_flag
        & row_deltas["expected_incremental_value_dollars_delta"].abs().gt(VALUE_SHADOW_VALUE_DELTA_MIN)
    )
    row_deltas["baseline_low_incremental_value_exclusion_flag"] = baseline_publish_reason.eq("do_not_order_low_incremental_value")
    row_deltas["shadow_low_incremental_value_exclusion_flag"] = row_deltas[
        "shadow_value_weak_promo_low_value_flag"
    ].fillna(0.0).ge(1.0)
    row_deltas["low_incremental_value_relief_flag"] = (
        row_deltas["baseline_low_incremental_value_exclusion_flag"]
        & ~row_deltas["shadow_low_incremental_value_exclusion_flag"]
        & row_deltas["expected_incremental_value_dollars_delta"].gt(VALUE_SHADOW_VALUE_DELTA_MIN)
    )
    row_deltas["baseline_do_not_order_flag"] = baseline_decision_action.eq("DO_NOT_ORDER")
    row_deltas["do_not_order_value_relief_flag"] = (
        row_deltas["baseline_do_not_order_flag"]
        & row_deltas["expected_incremental_value_dollars_delta"].gt(VALUE_SHADOW_VALUE_DELTA_MIN)
    )
    row_deltas["baseline_review_high_leftover_risk_flag"] = baseline_review_reason.eq("review_high_leftover_risk") | baseline_publish_reason.eq("review_high_leftover_risk")
    row_deltas["baseline_review_low_confidence_flag"] = baseline_review_reason.eq("review_low_confidence") | baseline_publish_reason.eq("review_low_confidence")
    row_deltas["review_high_leftover_value_relief_flag"] = (
        row_deltas["baseline_review_high_leftover_risk_flag"]
        & row_deltas["shadow_value_expected_leftover_above_trust_floor_units"].lt(
            row_deltas["baseline_value_expected_leftover_above_trust_floor_units"].fillna(0.0)
        )
    )
    row_deltas["review_low_confidence_value_relief_flag"] = False
    row_deltas["baseline_value_reason"] = baseline_publish_reason.where(
        baseline_publish_reason.ne(""),
        baseline_review_reason,
    )
    row_deltas["shadow_value_reason"] = row_deltas["baseline_value_reason"].where(
        ~row_deltas["low_incremental_value_relief_flag"],
        VALUE_SHADOW_RELIEVED_REASON,
    )
    row_deltas["value_shadow_blocker"] = _resolve_value_shadow_blocker(row_deltas)
    row_deltas["nearest_publishable_value_score"] = _resolve_value_shadow_flip_score(row_deltas)
    return row_deltas.sort_values(key_columns, kind="mergesort").reset_index(drop=True)


def _build_value_shadow_source_alignment_frame(frame: pd.DataFrame) -> pd.DataFrame:
    source = _prepare_feature_inspection_source_frame(frame)
    if source is None or source.empty:
        return pd.DataFrame(columns=[*SHADOW_JOIN_KEYS])
    expected_incremental_units = _first_non_null_numeric_frame_series(
        source,
        (
            "feature_expected_incremental_uplift_units_same_discount",
            "feature_uplift_units_expected_total",
            "feature_probability_uplift_supported_units",
        ),
        default=0.0,
    ).clip(lower=0.0)
    alignment = pd.DataFrame(
        {
            "store_number": _text_frame_series(source, ("store_number",), default=""),
            "promotion_header_key": _text_frame_series(source, ("promotion_header_key",), default=""),
            "sku_number": _text_frame_series(source, ("sku_number",), default=""),
            "source_expected_incremental_units": expected_incremental_units,
            "source_target_end_stock_units": _first_non_null_numeric_frame_series(
                source,
                ("feature_end_of_promo_target_units", "base_units_target"),
                default=2.0,
            ).clip(lower=0.0),
            "source_high_base_demand_flag": _first_non_null_numeric_frame_series(
                source,
                ("feature_high_base_demand_end_cover_flag", "feature_high_base_demand_cover_flag"),
                default=0.0,
            ).clip(lower=0.0, upper=1.0),
            "source_capital_at_risk": _first_non_null_numeric_frame_series(
                source,
                ("feature_capital_at_risk", "capital_at_risk"),
                default=0.0,
            ).clip(lower=0.0),
            "source_unit_cost": _first_non_null_numeric_frame_series(
                source,
                ("effective_cost_per_unit", "promo_effective_cost", "promo_cost_price", "last_received_cost"),
                default=0.0,
            ).clip(lower=0.0),
            "source_gross_profit_per_incremental_unit_expected": _first_non_null_numeric_frame_series(
                source,
                ("feature_gross_profit_per_incremental_unit_expected", "promo_gm_unit"),
                default=0.0,
            ),
            "source_historical_under_floor_missed_demand_rate": _first_non_null_numeric_frame_series(
                source,
                ("feature_historical_under_floor_missed_demand_rate",),
                default=0.0,
            ).clip(lower=0.0, upper=1.0),
            "source_historical_allocation_efficiency_rate": _first_non_null_numeric_frame_series(
                source,
                ("feature_historical_allocation_efficiency_rate",),
                default=np.nan,
            ).clip(lower=0.0, upper=1.0),
            "source_historical_overallocation_above_floor_rate": _first_non_null_numeric_frame_series(
                source,
                ("feature_historical_overallocation_above_floor_rate",),
                default=0.0,
            ).clip(lower=0.0, upper=1.0),
            "source_historical_trapped_capital_rate": _first_non_null_numeric_frame_series(
                source,
                ("feature_historical_trapped_capital_rate",),
                default=0.0,
            ).clip(lower=0.0, upper=1.0),
            "source_historical_sell_through": _first_non_null_numeric_frame_series(
                source,
                ("feature_historical_sell_through_on_accepted_qty",),
                default=np.nan,
            ).clip(lower=0.0, upper=1.0),
            "source_historical_comparable_event_count": _first_non_null_numeric_frame_series(
                source,
                ("feature_historical_comparable_promo_event_count",),
                default=0.0,
            ).clip(lower=0.0),
            "source_historical_zero_sale_after_buy_rate": _first_non_null_numeric_frame_series(
                source,
                ("feature_historical_zero_sale_after_buy_rate",),
                default=0.0,
            ).clip(lower=0.0, upper=1.0),
            "source_same_discount_success_rate": _first_non_null_numeric_frame_series(
                source,
                ("feature_same_discount_success_rate_56d",),
                default=np.nan,
            ).clip(lower=0.0, upper=1.0),
            "source_historical_overforecast_bias": _first_non_null_numeric_frame_series(
                source,
                ("feature_historical_overforecast_bias",),
                default=0.0,
            ).clip(lower=0.0, upper=1.0),
        }
    )
    return _collapse_shadow_alignment_frame(alignment)


def _build_value_shadow_metric_frame(
    *,
    row_frame: pd.DataFrame,
    expected_total_units: pd.Series,
    expected_incremental_units: pd.Series,
) -> pd.DataFrame:
    projected_available = (
        _numeric_frame_series(row_frame, ("current_soh_units",), default=0.0).fillna(0.0).clip(lower=0.0)
        + _numeric_frame_series(row_frame, ("qty_on_order_units",), default=0.0).fillna(0.0).clip(lower=0.0)
        - _numeric_frame_series(row_frame, ("predicted_units_until_promo_start",), default=0.0).fillna(0.0).clip(lower=0.0)
    ).clip(lower=0.0)
    expected_total = pd.to_numeric(expected_total_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    expected_incremental = pd.to_numeric(expected_incremental_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    target_end_stock = pd.to_numeric(row_frame["source_target_end_stock_units"], errors="coerce").fillna(2.0).clip(lower=0.0)
    high_base_flag = pd.to_numeric(row_frame["source_high_base_demand_flag"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    capital_at_risk = pd.to_numeric(row_frame["source_capital_at_risk"], errors="coerce").fillna(0.0).clip(lower=0.0)
    unit_cost = pd.to_numeric(row_frame["source_unit_cost"], errors="coerce").fillna(0.0).clip(lower=0.0)
    gross_profit_per_incremental = pd.to_numeric(
        row_frame["source_gross_profit_per_incremental_unit_expected"],
        errors="coerce",
    ).fillna(0.0)
    trust_metrics = _build_trust_floor_capital_metrics(
        projected_available_units_at_promo_start=projected_available,
        expected_total_units=expected_total,
        expected_incremental_units=expected_incremental,
        target_end_stock_units=target_end_stock,
        high_base_demand_flag=high_base_flag,
        capital_at_risk=capital_at_risk,
        unit_cost=unit_cost,
        gross_profit_per_incremental_unit_expected=gross_profit_per_incremental,
        historical_under_floor_missed_demand_rate=pd.to_numeric(
            row_frame["source_historical_under_floor_missed_demand_rate"],
            errors="coerce",
        ).fillna(0.0),
    )
    denominator = expected_total.where(expected_total.gt(0.0), 1.0)
    inventory_sufficiency_flag = projected_available.ge(expected_total).astype(float).where(projected_available.notna())
    expected_incremental_share = _safe_ratio(expected_incremental, denominator).clip(lower=0.0, upper=1.0)
    capital_at_risk_per_expected_unit = _safe_ratio(capital_at_risk, denominator)
    value_to_capital_ratio = _safe_ratio(
        gross_profit_per_incremental.clip(lower=0.0),
        capital_at_risk_per_expected_unit.where(capital_at_risk_per_expected_unit.gt(0.0)),
    )
    historical_signal_available = pd.to_numeric(
        row_frame["source_historical_comparable_event_count"],
        errors="coerce",
    ).fillna(0.0).ge(2.0)
    severe_history_failure_count = pd.concat(
        [
            pd.to_numeric(row_frame["source_historical_zero_sale_after_buy_rate"], errors="coerce").fillna(0.0).ge(0.25),
            pd.to_numeric(row_frame["source_same_discount_success_rate"], errors="coerce").le(0.35)
            & pd.to_numeric(row_frame["source_same_discount_success_rate"], errors="coerce").notna(),
            pd.to_numeric(row_frame["source_historical_trapped_capital_rate"], errors="coerce").fillna(0.0).ge(0.30),
            pd.to_numeric(row_frame["source_historical_sell_through"], errors="coerce").le(0.60)
            & pd.to_numeric(row_frame["source_historical_sell_through"], errors="coerce").notna(),
            pd.to_numeric(row_frame["source_historical_overforecast_bias"], errors="coerce").fillna(0.0).ge(0.25),
        ],
        axis=1,
    ).sum(axis=1).astype("float64")
    weak_low_value_flag = _build_weak_promo_low_value_flag(
        inventory_sufficiency_flag=inventory_sufficiency_flag,
        expected_incremental_share=expected_incremental_share,
        expected_incremental_units=expected_incremental,
        gross_profit_per_incremental_unit_expected=gross_profit_per_incremental,
        capital_at_risk_per_expected_unit=capital_at_risk_per_expected_unit,
        expected_gp_per_capital_committed=trust_metrics["feature_expected_gp_per_capital_committed"],
        stock_below_trust_floor_flag=trust_metrics["feature_stock_below_trust_floor_flag"],
        trust_floor_missed_demand_risk_score=trust_metrics["feature_trust_floor_missed_demand_risk_score"],
        speculative_above_trust_floor_risk_flag=trust_metrics["feature_speculative_above_trust_floor_risk_flag"],
        historical_signal_available=historical_signal_available,
        historical_allocation_efficiency_rate=pd.to_numeric(
            row_frame["source_historical_allocation_efficiency_rate"],
            errors="coerce",
        ),
        historical_overallocation_above_floor_rate=pd.to_numeric(
            row_frame["source_historical_overallocation_above_floor_rate"],
            errors="coerce",
        ).fillna(0.0),
        historical_trapped_capital_rate=pd.to_numeric(
            row_frame["source_historical_trapped_capital_rate"],
            errors="coerce",
        ).fillna(0.0),
        historical_sell_through=pd.to_numeric(row_frame["source_historical_sell_through"], errors="coerce"),
        severe_history_failure_count=severe_history_failure_count,
        value_to_capital_ratio=value_to_capital_ratio,
    )
    return pd.DataFrame(
        {
            "expected_total_units": expected_total,
            "expected_incremental_units": expected_incremental,
            "expected_incremental_value_dollars": (expected_incremental * gross_profit_per_incremental.clip(lower=0.0)).round(2),
            "expected_gp_on_trust_floor_units": trust_metrics["feature_expected_gp_on_trust_floor_units"].round(2),
            "expected_gp_on_speculative_units": trust_metrics["feature_expected_gp_on_speculative_units"].round(2),
            "risk_adjusted_value_of_speculative_units": trust_metrics["feature_risk_adjusted_value_of_speculative_units"].round(2),
            "speculative_capital_above_floor_units": trust_metrics["feature_expected_leftover_above_trust_floor_units"].round(4),
            "expected_leftover_above_trust_floor_units": trust_metrics["feature_expected_leftover_above_trust_floor_units"].round(4),
            "expected_gp_per_capital_committed": trust_metrics["feature_expected_gp_per_capital_committed"].round(4),
            "weak_promo_low_value_flag": weak_low_value_flag.fillna(0.0),
        },
        index=row_frame.index,
    )


def _resolve_value_shadow_blocker(row_deltas: pd.DataFrame) -> pd.Series:
    value_changed = row_deltas["expected_incremental_value_dollars_delta"].abs().gt(VALUE_SHADOW_VALUE_DELTA_MIN)
    blocker = pd.Series("no_value_shadow_change", index=row_deltas.index, dtype="object")
    blocker = blocker.where(~(value_changed & row_deltas["stock_gap_flag"].fillna(False).astype(bool)), "stock_gap_policy")
    blocker = blocker.where(
        ~(value_changed & row_deltas["sparse_history_flag"].fillna(False).astype(bool) & blocker.eq("no_value_shadow_change")),
        "sparse_history_review",
    )
    blocker = blocker.where(
        ~(value_changed & row_deltas["baseline_review_high_leftover_risk_flag"] & blocker.eq("no_value_shadow_change")),
        "leftover_risk_review",
    )
    blocker = blocker.where(
        ~(value_changed & row_deltas["baseline_review_low_confidence_flag"] & blocker.eq("no_value_shadow_change")),
        "confidence_review",
    )
    blocker = blocker.where(~(value_changed & blocker.eq("no_value_shadow_change")), "value_relief_no_publish_effect")
    blocker = blocker.where(~row_deltas["non_gated_value_delta_leak_flag"], "non_gated_value_leak")
    return blocker


def _resolve_value_shadow_flip_score(row_deltas: pd.DataFrame) -> pd.Series:
    value_gap = (-pd.to_numeric(row_deltas["shadow_value_expected_incremental_value_dollars"], errors="coerce").fillna(0.0)).clip(lower=0.0)
    low_value_penalty = row_deltas["shadow_low_incremental_value_exclusion_flag"].astype(int)
    stock_gap_penalty = row_deltas["stock_gap_flag"].fillna(False).astype(bool).astype(int)
    confidence_penalty = row_deltas["baseline_review_low_confidence_flag"].astype(int) * 0.5
    leftover_penalty = row_deltas["baseline_review_high_leftover_risk_flag"].astype(int) * 0.5
    publish_penalty = row_deltas["publish_bucket"].ne("publish_eligible").astype(int)
    value_relief_bonus = row_deltas["expected_incremental_value_dollars_delta"].clip(lower=0.0) / 100.0
    return publish_penalty + low_value_penalty + stock_gap_penalty + confidence_penalty + leftover_penalty + value_gap - value_relief_bonus


def _build_specialist_value_shadow_reason_transitions(row_deltas: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_dimensions = {"all": None, **VALUE_SHADOW_GROUP_DIMENSIONS, "low_nonzero_gated_rows": "low_nonzero_gate_flag"}
    for group_dimension, column_name in group_dimensions.items():
        work = row_deltas.copy()
        work["group_value"] = "all" if column_name is None else work[column_name].fillna("unknown").astype(str)
        grouped = work.groupby(["group_value", "baseline_value_reason", "shadow_value_reason"], dropna=False)
        for (group_value, baseline_reason, shadow_reason), group in grouped:
            rows.append(
                {
                    "group_dimension": group_dimension,
                    "group_value": str(group_value),
                    "baseline_value_reason": str(baseline_reason),
                    "shadow_value_reason": str(shadow_reason),
                    "row_count": int(len(group.index)),
                    "low_nonzero_gate_row_count": int(group["low_nonzero_gate_flag"].sum()),
                    "expected_incremental_value_changed_row_count": int(
                        group["expected_incremental_value_dollars_delta"].abs().gt(VALUE_SHADOW_VALUE_DELTA_MIN).sum()
                    ),
                    "do_not_order_low_incremental_value_relief_row_count": int(group["low_incremental_value_relief_flag"].sum()),
                    "do_not_order_value_relief_row_count": int(group["do_not_order_value_relief_flag"].sum()),
                    "review_high_leftover_value_relief_row_count": int(group["review_high_leftover_value_relief_flag"].sum()),
                    "review_low_confidence_value_relief_row_count": int(group["review_low_confidence_value_relief_flag"].sum()),
                    "avg_expected_incremental_value_delta": _maybe_float(group["expected_incremental_value_dollars_delta"].mean()),
                    "avg_risk_adjusted_speculative_value_delta": _maybe_float(group["risk_adjusted_value_of_speculative_units_delta"].mean()),
                }
            )
    return pd.DataFrame(rows)


def _build_specialist_value_shadow_flip_candidates(row_deltas: pd.DataFrame) -> pd.DataFrame:
    candidates = row_deltas.loc[
        row_deltas["publish_bucket"].ne("publish_eligible")
        & row_deltas["low_nonzero_gate_flag"]
        & row_deltas["expected_incremental_value_dollars_delta"].gt(VALUE_SHADOW_VALUE_DELTA_MIN)
    ].copy()
    columns = [
        "store_number",
        "promotion_header_key",
        "sku_number",
        "promotion_name",
        "promo_type",
        "publish_bucket",
        "publish_reason",
        "review_reason",
        "decision_action",
        "baseline_value_reason",
        "shadow_value_reason",
        "value_shadow_blocker",
        "nearest_publishable_value_score",
        "baseline_value_expected_incremental_value_dollars",
        "shadow_value_expected_incremental_value_dollars",
        "expected_incremental_value_dollars_delta",
        "baseline_value_risk_adjusted_value_of_speculative_units",
        "shadow_value_risk_adjusted_value_of_speculative_units",
        "risk_adjusted_value_of_speculative_units_delta",
        "baseline_low_incremental_value_exclusion_flag",
        "shadow_low_incremental_value_exclusion_flag",
        "low_incremental_value_relief_flag",
        "do_not_order_value_relief_flag",
        "review_high_leftover_value_relief_flag",
        "review_low_confidence_value_relief_flag",
    ]
    available = [column_name for column_name in columns if column_name in candidates.columns]
    return candidates.sort_values(
        by=["nearest_publishable_value_score", "expected_incremental_value_dollars_delta"],
        ascending=[True, False],
        kind="mergesort",
    ).loc[:, available]


def _build_specialist_value_shadow_summary(
    *,
    run_id: str,
    as_of_date: str,
    row_deltas: pd.DataFrame,
    reason_transitions: pd.DataFrame,
    flip_candidates: pd.DataFrame,
    scenario_summary_frame: pd.DataFrame,
) -> dict[str, object]:
    baseline_scenario = scenario_summary_frame.loc[
        scenario_summary_frame["scenario_id"].eq(SCENARIO_CURRENT_SLIM)
    ].iloc[0]
    shadow_scenario = scenario_summary_frame.loc[
        scenario_summary_frame["scenario_id"].eq(SCENARIO_GATED)
    ].iloc[0]
    value_changed = row_deltas["expected_incremental_value_dollars_delta"].abs().gt(VALUE_SHADOW_VALUE_DELTA_MIN)
    low_nonzero_gate = row_deltas["low_nonzero_gate_flag"].astype(bool)
    top_blockers = row_deltas.loc[value_changed].groupby("value_shadow_blocker", dropna=False).agg(
        row_count=("value_shadow_blocker", "size"),
        low_nonzero_gate_row_count=("low_nonzero_gate_flag", "sum"),
        do_not_order_low_incremental_value_relief_row_count=("low_incremental_value_relief_flag", "sum"),
        do_not_order_value_relief_row_count=("do_not_order_value_relief_flag", "sum"),
        avg_expected_incremental_value_delta=("expected_incremental_value_dollars_delta", "mean"),
    ).reset_index().sort_values(by=["row_count", "avg_expected_incremental_value_delta"], ascending=[False, False], kind="mergesort")
    summary = {
        "run_id": run_id,
        "as_of_date": as_of_date,
        "row_count": int(len(row_deltas.index)),
        "low_nonzero_gate_row_count": int(low_nonzero_gate.sum()),
        "expected_incremental_value_changed_row_count": int(value_changed.sum()),
        "expected_incremental_value_changed_non_gated_row_count": int((value_changed & ~low_nonzero_gate).sum()),
        "forecast_source_priority_changed_row_count": int(row_deltas["forecast_source_priority_changed_flag"].sum()),
        "commercial_predicted_units_changed_row_count": int(row_deltas["commercial_predicted_units_changed_flag"].sum()),
        "buy_order_widening_row_count": int(row_deltas["buy_order_widening_flag"].sum()),
        "stage12_publishability_widening_row_count": int(row_deltas["stage12_publishability_widening_flag"].sum()),
        "do_not_order_low_incremental_value_baseline_row_count": int(row_deltas["baseline_low_incremental_value_exclusion_flag"].sum()),
        "do_not_order_low_incremental_value_shadow_row_count": int(row_deltas["shadow_low_incremental_value_exclusion_flag"].sum()),
        "do_not_order_low_incremental_value_relief_row_count": int(row_deltas["low_incremental_value_relief_flag"].sum()),
        "do_not_order_baseline_row_count": int(row_deltas["baseline_do_not_order_flag"].sum()),
        "do_not_order_value_relief_row_count": int(row_deltas["do_not_order_value_relief_flag"].sum()),
        "review_high_leftover_risk_baseline_row_count": int(row_deltas["baseline_review_high_leftover_risk_flag"].sum()),
        "review_high_leftover_value_relief_row_count": int(row_deltas["review_high_leftover_value_relief_flag"].sum()),
        "review_low_confidence_baseline_row_count": int(row_deltas["baseline_review_low_confidence_flag"].sum()),
        "review_low_confidence_value_relief_row_count": int(row_deltas["review_low_confidence_value_relief_flag"].sum()),
        "non_gated_value_delta_leak_row_count": int(row_deltas["non_gated_value_delta_leak_flag"].sum()),
        "total_expected_incremental_value_delta": _maybe_float(row_deltas["expected_incremental_value_dollars_delta"].sum()),
        "total_risk_adjusted_speculative_value_delta": _maybe_float(row_deltas["risk_adjusted_value_of_speculative_units_delta"].sum()),
        "value_shadow_blocker_counts": {
            str(key): int(value)
            for key, value in row_deltas["value_shadow_blocker"].astype(str).value_counts(dropna=False).to_dict().items()
        },
        "top_blocker_mechanisms": top_blockers.head(10).to_dict(orient="records"),
        "flip_candidate_count": int(len(flip_candidates.index)),
        "top_flip_candidates": flip_candidates.head(25).to_dict(orient="records"),
        "grouped_value_highlights": _build_value_shadow_group_highlights(row_deltas),
        "reason_transition_highlights": reason_transitions.loc[
            reason_transitions["group_dimension"].eq("all")
        ].sort_values(by=["row_count"], ascending=[False], kind="mergesort").head(20).to_dict(orient="records"),
        "baseline_metrics": {
            "mae": _maybe_float(baseline_scenario.get("mae")),
            "overforecast_rate": _maybe_float(baseline_scenario.get("overforecast_rate")),
        },
        "gated_shadow_metrics": {
            "mae": _maybe_float(shadow_scenario.get("mae")),
            "overforecast_rate": _maybe_float(shadow_scenario.get("overforecast_rate")),
        },
        "diagnostics_only_flag": True,
    }
    recommendation, rationale = _resolve_value_shadow_recommendation(summary)
    summary["recommendation"] = recommendation
    summary["recommendation_rationale"] = rationale
    return summary


def _build_value_shadow_group_highlights(row_deltas: pd.DataFrame) -> dict[str, list[dict[str, object]]]:
    group_dimensions = {**VALUE_SHADOW_GROUP_DIMENSIONS, "low_nonzero_gated_rows": "low_nonzero_gate_flag"}
    highlights: dict[str, list[dict[str, object]]] = {}
    for group_dimension, column_name in group_dimensions.items():
        work = row_deltas.copy()
        work["group_value"] = work[column_name].fillna("unknown").astype(str)
        grouped = work.groupby(["group_value", "value_shadow_blocker"], dropna=False).agg(
            row_count=("value_shadow_blocker", "size"),
            value_changed_row_count=("expected_incremental_value_dollars_delta", lambda series: int(series.abs().gt(VALUE_SHADOW_VALUE_DELTA_MIN).sum())),
            do_not_order_low_incremental_value_relief_row_count=("low_incremental_value_relief_flag", "sum"),
            do_not_order_value_relief_row_count=("do_not_order_value_relief_flag", "sum"),
            review_high_leftover_value_relief_row_count=("review_high_leftover_value_relief_flag", "sum"),
            review_low_confidence_value_relief_row_count=("review_low_confidence_value_relief_flag", "sum"),
            avg_expected_incremental_value_delta=("expected_incremental_value_dollars_delta", "mean"),
        ).reset_index().sort_values(
            by=["value_changed_row_count", "row_count", "avg_expected_incremental_value_delta"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        highlights[group_dimension] = grouped.head(10).to_dict(orient="records")
    return highlights


def _build_specialist_value_shadow_brief(summary: dict[str, object]) -> str:
    lines = [
        f"# Specialist Value Shadow: {summary['run_id']}",
        "",
        "## Value-Only Shadow Result",
        f"- Low-nonzero gated rows: `{summary['low_nonzero_gate_row_count']}`",
        f"- Expected incremental value changed rows: `{summary['expected_incremental_value_changed_row_count']}`",
        f"- Non-gated value delta leaks: `{summary['non_gated_value_delta_leak_row_count']}`",
        f"- Total expected incremental value delta: `{summary['total_expected_incremental_value_delta']}`",
        f"- Total risk-adjusted speculative value delta: `{summary['total_risk_adjusted_speculative_value_delta']}`",
        "",
        "## Governance Invariants",
        f"- Forecast-source priority changed rows: `{summary['forecast_source_priority_changed_row_count']}`",
        f"- Commercial predicted-units changed rows: `{summary['commercial_predicted_units_changed_row_count']}`",
        f"- BUY/ORDER widening rows: `{summary['buy_order_widening_row_count']}`",
        f"- Stage 12 publishability widening rows: `{summary['stage12_publishability_widening_row_count']}`",
        "",
        "## Value Relief",
        f"- `do_not_order_low_incremental_value` baseline/shadow/relief: `{summary['do_not_order_low_incremental_value_baseline_row_count']}` / `{summary['do_not_order_low_incremental_value_shadow_row_count']}` / `{summary['do_not_order_low_incremental_value_relief_row_count']}`",
        f"- `do_not_order` baseline/value-relief: `{summary['do_not_order_baseline_row_count']}` / `{summary['do_not_order_value_relief_row_count']}`",
        f"- `review_high_leftover_risk` baseline/value-relief: `{summary['review_high_leftover_risk_baseline_row_count']}` / `{summary['review_high_leftover_value_relief_row_count']}`",
        f"- `review_low_confidence` baseline/value-relief: `{summary['review_low_confidence_baseline_row_count']}` / `{summary['review_low_confidence_value_relief_row_count']}`",
        "",
        "## Recommendation",
        f"- Recommendation: `{summary['recommendation']}`",
        f"- Rationale: {summary['recommendation_rationale']}",
    ]
    return "\n".join(lines) + "\n"


def _resolve_value_shadow_recommendation(summary: dict[str, object]) -> tuple[str, str]:
    value_changed = int(summary.get("expected_incremental_value_changed_row_count", 0))
    non_gated_leaks = int(summary.get("non_gated_value_delta_leak_row_count", 0))
    widening = int(summary.get("buy_order_widening_row_count", 0)) + int(summary.get("stage12_publishability_widening_row_count", 0))
    low_value_relief = int(summary.get("do_not_order_low_incremental_value_relief_row_count", 0))
    do_not_order_relief = int(summary.get("do_not_order_value_relief_row_count", 0))
    if widening > 0 or non_gated_leaks > 0:
        return (
            "reject operationalization for now",
            "The diagnostics-only value shadow violated a governance invariant and should not be routed forward.",
        )
    if value_changed > 0 and (low_value_relief > 0 or do_not_order_relief > 0):
        return (
            "route specialist into downstream value calculation seam",
            "The specialist creates value relief inside the governed low-nonzero gate while forecast-source priority, BUY/ORDER actions, and Stage 12 publishability remain unchanged.",
        )
    if value_changed > 0:
        return (
            "keep specialist as shadow-calibration only",
            "The specialist changes value metrics, but the pass does not yet show relief on low-incremental-value or no-order diagnostics.",
        )
    return (
        "reject operationalization for now",
        "The value-only shadow did not surface economic movement beyond the existing calibration result.",
    )


def _first_non_null_numeric_frame_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
    *,
    default: float | int | None = 0.0,
) -> pd.Series:
    present = [column_name for column_name in column_names if column_name in frame.columns]
    if not present:
        return pd.Series(default, index=frame.index, dtype="float64")
    candidate_frame = frame[present].apply(pd.to_numeric, errors="coerce")
    return candidate_frame.bfill(axis=1).iloc[:, 0]


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator_numeric = pd.to_numeric(numerator, errors="coerce")
    denominator_numeric = pd.to_numeric(denominator, errors="coerce")
    return numerator_numeric.divide(denominator_numeric.where(denominator_numeric.ne(0.0))).replace([np.inf, -np.inf], np.nan)


def _resolve_publish_flip_gap_score(row_deltas: pd.DataFrame) -> pd.Series:
    confidence_gap = (PUBLISH_CONFIDENCE_FLOOR - pd.to_numeric(row_deltas["shadow_final_confidence_score"], errors="coerce").fillna(0.0)).clip(lower=0.0)
    stock_gap = pd.to_numeric(row_deltas["shadow_projected_stock_gap_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    expected_value_gap = (-pd.to_numeric(row_deltas["shadow_expected_incremental_value_dollars"], errors="coerce").fillna(0.0)).clip(lower=0.0)
    trust_gap = row_deltas["shadow_trust_floor_risk_flag"].fillna(False).astype(bool).astype(int)
    publish_penalty = row_deltas["shadow_publish_bucket"].eq("excluded_legitimate").astype(int) + row_deltas["shadow_publish_bucket"].eq("review_only").astype(int) * 0.5
    return publish_penalty + confidence_gap + stock_gap + expected_value_gap + trust_gap


def _interesting_shadow_rows(
    row_deltas: pd.DataFrame,
    *,
    limit: int,
    sort_columns: list[str] | None = None,
    ascending: list[bool] | None = None,
) -> list[dict[str, object]]:
    if row_deltas.empty:
        return []
    work = row_deltas.copy()
    if sort_columns:
        work = work.sort_values(by=sort_columns, ascending=ascending or [False] * len(sort_columns), kind="mergesort")
    columns = [
        "store_number",
        "promotion_header_key",
        "sku_number",
        "promotion_name",
        "promo_type",
        "baseline_publish_bucket",
        "shadow_publish_bucket",
        "baseline_publish_reason",
        "shadow_publish_reason",
        "baseline_recommendation_reason",
        "shadow_recommendation_reason",
        "raw_predicted_units_delta",
        "predicted_units_total_promo_delta",
        "expected_incremental_value_dollars_delta",
        "final_confidence_score_delta",
        "blocker_category",
        "blocker_mechanism",
        "publish_flip_gap_score",
    ]
    available = [column_name for column_name in columns if column_name in work.columns]
    return work.loc[:, available].head(limit).to_dict(orient="records")


def _prefix_alignment_columns(frame: pd.DataFrame, *, prefix: str, key_columns: list[str]) -> pd.DataFrame:
    rename_map = {
        column_name: f"{prefix}_{column_name}"
        for column_name in frame.columns
        if column_name not in key_columns
    }
    return frame.rename(columns=rename_map)


def _collapse_shadow_alignment_frame(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    for column_name in SHADOW_JOIN_KEYS:
        work[column_name] = work[column_name].fillna("").astype(str)
    sort_columns = [column_name for column_name in ("promotion_row_key",) if column_name in work.columns]
    if sort_columns:
        work = work.sort_values(by=sort_columns, kind="mergesort")
    return work.drop_duplicates(subset=list(SHADOW_JOIN_KEYS), keep="first").reset_index(drop=True)


def _numeric_frame_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
    *,
    default: float | int | None = 0.0,
) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return pd.to_numeric(frame[column_name], errors="coerce")
    return pd.Series(default, index=frame.index, dtype="float64")


def _text_frame_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
    *,
    default: str = "",
) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return frame[column_name].fillna(default).astype(str)
    return pd.Series(default, index=frame.index, dtype="object")


def _bool_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    return _numeric_frame_series(frame, column_names, default=0.0).fillna(0.0).ge(1.0)


def _resolve_expected_incremental_value_series(frame: pd.DataFrame) -> pd.Series:
    for candidate_columns in (
        ("expected_incremental_value_dollars",),
        ("expected_gp_on_speculative_units",),
        ("risk_adjusted_value_of_speculative_units",),
    ):
        for column_name in candidate_columns:
            if column_name in frame.columns:
                return pd.to_numeric(frame[column_name], errors="coerce")
    return pd.Series(0.0, index=frame.index, dtype="float64")


def _build_recommendation_markdown(
    *,
    run_id: str,
    scenario_summary_frame: pd.DataFrame,
    classifier_diagnostics: LowNonzeroSpecialistClassifierDiagnostics,
    config: LowNonzeroSpecialistConfig,
) -> str:
    baseline = scenario_summary_frame.loc[scenario_summary_frame["scenario_id"].eq(SCENARIO_CURRENT_SLIM)].iloc[0]
    specialist = scenario_summary_frame.loc[scenario_summary_frame["scenario_id"].eq(SCENARIO_SPECIALIST)].iloc[0]
    gated = scenario_summary_frame.loc[scenario_summary_frame["scenario_id"].eq(SCENARIO_GATED)].iloc[0]

    low_nonzero_overforecast_delta = (baseline["low_nonzero_overforecast_rate"] or 0.0) - (gated["low_nonzero_overforecast_rate"] or 0.0)
    publish_delta = int(gated["publish_eligible_row_count"]) - int(baseline["publish_eligible_row_count"])
    review_delta = int(gated["review_only_row_count"]) - int(baseline["review_only_row_count"])
    low_value_delta = int(gated["do_not_order_low_incremental_value_row_count"]) - int(baseline["do_not_order_low_incremental_value_row_count"])

    if low_nonzero_overforecast_delta >= 0.05 and publish_delta > 0 and low_value_delta < 0 and review_delta <= 0:
        recommendation = "replace sparse cohort path"
    elif low_nonzero_overforecast_delta > 0.0 or publish_delta > 0 or low_value_delta < 0:
        recommendation = "keep specialist as calibration-only"
    else:
        recommendation = "reject"

    lines = [
        f"# Low-Nonzero Specialist Recommendation: {run_id}",
        "",
        f"- Runtime version: `{SPECIALIST_RUNTIME_VERSION}`",
        f"- Conservative objective: `LightGBM quantile` with `alpha={config.quantile_alpha}`",
        f"- Core feature families: `{', '.join(specialist_feature_family_names(resolve_specialist_feature_columns(config=config)))}`",
        "",
        "## Scenario Comparison",
        f"- Baseline low-nonzero overforecast rate: `{baseline['low_nonzero_overforecast_rate']}`",
        f"- Specialist-only low-nonzero overforecast rate: `{specialist['low_nonzero_overforecast_rate']}`",
        f"- Gated low-nonzero overforecast rate: `{gated['low_nonzero_overforecast_rate']}`",
        f"- Publish-eligible rows: baseline `{baseline['publish_eligible_row_count']}`, specialist `{specialist['publish_eligible_row_count']}`, gated `{gated['publish_eligible_row_count']}`",
        f"- Review-only rows: baseline `{baseline['review_only_row_count']}`, specialist `{specialist['review_only_row_count']}`, gated `{gated['review_only_row_count']}`",
        f"- `do_not_order_low_incremental_value` rows: baseline `{baseline['do_not_order_low_incremental_value_row_count']}`, specialist `{specialist['do_not_order_low_incremental_value_row_count']}`, gated `{gated['do_not_order_low_incremental_value_row_count']}`",
        "",
        "## Diagnostic Classifier",
        f"- Label source: `{classifier_diagnostics.label_source}`",
        f"- Train rows: `{classifier_diagnostics.train_row_count}`; evaluation rows: `{classifier_diagnostics.evaluation_row_count}`",
        f"- Accuracy: `{classifier_diagnostics.accuracy}`; macro-F1: `{classifier_diagnostics.macro_f1}`",
        "",
        "## Recommendation",
        f"- Recommendation: `{recommendation}`",
        "- Rationale: this pass is diagnostics-only and leaves the default slim units head, Stage 12 publish logic, and policy thresholds unchanged.",
    ]
    return "\n".join(lines) + "\n"


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())