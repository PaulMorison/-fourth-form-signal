from __future__ import annotations

"""CLI entrypoint for governed promotions decision-surface execution."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
import argparse
from contextlib import nullcontext
import json
import logging
from pathlib import Path

import pandas as pd

from models.promotions.cohorts import (
    CohortSimilarityConfig,
    PromotionArchetypeRanker,
    PromotionArchetypeRankingResult,
    PromotionCohortBacktestResult,
    PromotionCohortBacktester,
    PromotionCohortSimilarity,
    PromotionDecisionCalibrator,
    PromotionDecisionDiagnostics,
    PromotionDecisionFusion,
    PromotionDecisionFusionConfig,
)
from runtime.promotions.artifact_compatibility import (
    PromotionArtifactCompatibilityResult,
    assert_artifact_compatibility,
)
from runtime.promotions.artifact_locator import (
    ResolvedPromotionModelBundle,
    ResolvedPromotionTrainingReadyArtifact,
    resolve_model_bundle,
    resolve_training_ready_artifact,
)
from runtime.promotions.config import PromotionArtifactPaths
from runtime.promotions.decision_surface_service import (
    empty_cohort_match_frame,
    load_training_ready_artifact,
    score_training_ready_rows,
)
from runtime.promotions.operator_progress import PromotionOperatorProgress
from state.promotions.cohorts import PromotionCohortAssigner, PromotionCohortHistoryBuilder
from surfaces.promotions.reporting import (
    PromotionCohortReportBuilder,
    PromotionDecisionSurfaceInspectionBuilder,
    PromotionDecisionSurfaceReportBuilder,
)


LOGGER = logging.getLogger(__name__)
PROMOTION_DECISION_SURFACE_VERSION = "promotions_decision_surface_v2"


@dataclass(frozen=True)
class PromotionDecisionSurfaceRunArtifacts:
    decision_surface_manifest_path: str
    decision_surface_metrics_path: str
    diagnostics_summary_path: str
    calibration_summary_path: str
    calibration_thresholds_path: str
    execution_summary_path: str
    inspection_manifest_path: str
    report_paths: dict[str, dict[str, str]]
    inspection_report_paths: dict[str, dict[str, str]]
    cohort_report_manifest_path: str | None


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    artifacts = run_decision_surface(
        dataset_path=args.dataset_path,
        dataset_run_id=args.dataset_run_id,
        model_bundle_path=args.model_bundle_path,
        model_run_id=args.model_run_id,
        artifact_root=args.artifact_root,
        run_id=args.run_id,
        as_of_date=args.as_of_date,
        minimum_cohort_sample_size=args.minimum_cohort_sample_size,
        similarity_threshold=args.similarity_threshold,
        archetype_confidence_floor=args.archetype_confidence_floor,
        row_model_confidence_floor=args.row_model_confidence_floor,
    )
    LOGGER.info(
        "Completed promotions decision surface: manifest=%s metrics=%s",
        artifacts.decision_surface_manifest_path,
        artifacts.decision_surface_metrics_path,
    )


def run_decision_surface(
    *,
    dataset_path: str | None,
    dataset_run_id: str | None = None,
    model_bundle_path: str | None,
    model_run_id: str | None = None,
    artifact_root: str | None,
    run_id: str,
    as_of_date: str | None,
    minimum_cohort_sample_size: int,
    similarity_threshold: float | None,
    archetype_confidence_floor: float | None,
    row_model_confidence_floor: float | None,
    operator_progress: PromotionOperatorProgress | None = None,
    decision_surface_stage_number: int | None = None,
    inspection_stage_number: int | None = None,
    total_stages: int | None = None,
) -> PromotionDecisionSurfaceRunArtifacts:
    """Execute the governed decision-surface flow against a persisted training-ready artifact."""

    artifact_paths = PromotionArtifactPaths.from_env(root=Path(artifact_root) if artifact_root else None)
    if (
        operator_progress is not None
        and decision_surface_stage_number is not None
        and total_stages is not None
    ):
        operator_progress.start_stage(
            decision_surface_stage_number,
            total_stages,
            "Build decision surface",
        )
        operator_progress.detail(
            "sub-task: loading governed training-ready and model artifacts for decision-surface execution"
        )
    resolved_dataset_artifact = resolve_training_ready_artifact(
        artifact_paths=artifact_paths,
        dataset_path=dataset_path,
        dataset_run_id=dataset_run_id,
    )
    resolved_model_bundle = resolve_model_bundle(
        artifact_paths=artifact_paths,
        model_bundle_path=model_bundle_path,
        model_run_id=model_run_id,
    )
    compatibility_result = assert_artifact_compatibility(
        dataset_artifact=resolved_dataset_artifact,
        model_bundle=resolved_model_bundle,
    )
    dataset_artifact = load_training_ready_artifact(resolved_dataset_artifact.dataset_path)
    decision_as_of_date = date.fromisoformat(as_of_date) if as_of_date else datetime.now(tz=UTC).date()
    if dataset_artifact.frame.empty:
        raise ValueError("Decision-surface execution requires a non-empty training-ready dataset artifact.")

    row_model_artifacts = score_training_ready_rows(
        dataset_artifact.frame.copy(),
        model_bundle_path=resolved_model_bundle.model_bundle_path,
    )
    return _run_decision_surface_from_frames(
        evaluation_scored_frame=row_model_artifacts.scored_frame.copy(),
        historical_reference_frame=row_model_artifacts.scored_frame.copy(),
        use_backtest_matches_for_evaluation=True,
        artifact_paths=artifact_paths,
        run_id=run_id,
        decision_as_of_date=decision_as_of_date,
        minimum_cohort_sample_size=minimum_cohort_sample_size,
        similarity_threshold=similarity_threshold,
        archetype_confidence_floor=archetype_confidence_floor,
        row_model_confidence_floor=row_model_confidence_floor,
        resolved_dataset_artifact=resolved_dataset_artifact,
        resolved_model_bundle=resolved_model_bundle,
        compatibility_result=compatibility_result,
        evaluation_feature_column_count=row_model_artifacts.feature_column_count,
        operator_progress=operator_progress,
        decision_surface_stage_number=decision_surface_stage_number,
        inspection_stage_number=inspection_stage_number,
        total_stages=total_stages,
    )


def run_decision_surface_for_scored_rows(
    *,
    future_scored_frame: pd.DataFrame,
    historical_dataset_path: str | None,
    historical_dataset_run_id: str | None = None,
    model_bundle_path: str | None,
    model_run_id: str | None = None,
    artifact_root: str | None,
    run_id: str,
    as_of_date: str | None,
    minimum_cohort_sample_size: int,
    similarity_threshold: float | None,
    archetype_confidence_floor: float | None,
    row_model_confidence_floor: float | None,
    operator_progress: PromotionOperatorProgress | None = None,
    decision_surface_stage_number: int | None = None,
    inspection_stage_number: int | None = None,
    total_stages: int | None = None,
) -> PromotionDecisionSurfaceRunArtifacts:
    """Execute the decision surface for future scored rows using historical cohort context."""

    artifact_paths = PromotionArtifactPaths.from_env(root=Path(artifact_root) if artifact_root else None)
    if (
        operator_progress is not None
        and decision_surface_stage_number is not None
        and total_stages is not None
    ):
        operator_progress.start_stage(
            decision_surface_stage_number,
            total_stages,
            "Build decision surface",
        )
        operator_progress.detail(
            "action: load future scored rows, historical cohort context, and governed model artifacts"
        )
    resolved_dataset_artifact = resolve_training_ready_artifact(
        artifact_paths=artifact_paths,
        dataset_path=historical_dataset_path,
        dataset_run_id=historical_dataset_run_id,
    )
    resolved_model_bundle = resolve_model_bundle(
        artifact_paths=artifact_paths,
        model_bundle_path=model_bundle_path,
        model_run_id=model_run_id,
    )
    compatibility_result = assert_artifact_compatibility(
        dataset_artifact=resolved_dataset_artifact,
        model_bundle=resolved_model_bundle,
    )
    historical_dataset_artifact = load_training_ready_artifact(
        resolved_dataset_artifact.dataset_path
    )
    decision_as_of_date = date.fromisoformat(as_of_date) if as_of_date else datetime.now(tz=UTC).date()
    if historical_dataset_artifact.frame.empty:
        raise ValueError(
            "Decision-surface execution requires a non-empty historical training-ready dataset artifact."
        )
    if future_scored_frame.empty:
        raise ValueError("Decision-surface execution requires non-empty future scored rows.")
    if "row_model_confidence_score" not in future_scored_frame.columns:
        raise ValueError(
            "Future scored rows are missing row_model_confidence_score. Use PromotionModelScorer output directly before building the live decision surface."
        )

    historical_row_model_artifacts = score_training_ready_rows(
        historical_dataset_artifact.frame.copy(),
        model_bundle_path=resolved_model_bundle.model_bundle_path,
    )
    evaluation_feature_column_count = len(
        [
            column_name
            for column_name in future_scored_frame.columns
            if str(column_name).startswith("feature_")
        ]
    )
    return _run_decision_surface_from_frames(
        evaluation_scored_frame=future_scored_frame.copy(),
        historical_reference_frame=historical_row_model_artifacts.scored_frame.copy(),
        use_backtest_matches_for_evaluation=False,
        artifact_paths=artifact_paths,
        run_id=run_id,
        decision_as_of_date=decision_as_of_date,
        minimum_cohort_sample_size=minimum_cohort_sample_size,
        similarity_threshold=similarity_threshold,
        archetype_confidence_floor=archetype_confidence_floor,
        row_model_confidence_floor=row_model_confidence_floor,
        resolved_dataset_artifact=resolved_dataset_artifact,
        resolved_model_bundle=resolved_model_bundle,
        compatibility_result=compatibility_result,
        evaluation_feature_column_count=evaluation_feature_column_count,
        operator_progress=operator_progress,
        decision_surface_stage_number=decision_surface_stage_number,
        inspection_stage_number=inspection_stage_number,
        total_stages=total_stages,
    )


def _run_decision_surface_from_frames(
    *,
    evaluation_scored_frame: pd.DataFrame,
    historical_reference_frame: pd.DataFrame,
    use_backtest_matches_for_evaluation: bool,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    decision_as_of_date: date,
    minimum_cohort_sample_size: int,
    similarity_threshold: float | None,
    archetype_confidence_floor: float | None,
    row_model_confidence_floor: float | None,
    resolved_dataset_artifact: ResolvedPromotionTrainingReadyArtifact,
    resolved_model_bundle: ResolvedPromotionModelBundle,
    compatibility_result: PromotionArtifactCompatibilityResult,
    evaluation_feature_column_count: int,
    operator_progress: PromotionOperatorProgress | None,
    decision_surface_stage_number: int | None,
    inspection_stage_number: int | None,
    total_stages: int | None,
) -> PromotionDecisionSurfaceRunArtifacts:
    decision_surface_context = (
        operator_progress.heartbeat(
            "assigning cohorts, backtesting archetypes, calibrating thresholds, and writing decision-surface tables",
            heartbeat_seconds=10.0,
            row_count=int(len(evaluation_scored_frame.index)),
        )
        if operator_progress is not None
        else nullcontext()
    )
    with decision_surface_context:
        assigned_evaluation_frame = PromotionCohortAssigner().assign(
            evaluation_scored_frame
        ).frame
        similarity_seed_threshold = float(similarity_threshold or 0.55)
        cohort_history = None
        backtest_result: PromotionCohortBacktestResult | None = None
        ranking_result = PromotionArchetypeRankingResult(
            rankings_frame=pd.DataFrame(),
            failure_watchlist_frame=pd.DataFrame(),
        )
        cohort_report_artifacts = None
        if operator_progress is not None:
            operator_progress.update_heartbeat(
                subtask="building cohort history and archetype rankings from historical reference rows"
            )
        try:
            cohort_history = PromotionCohortHistoryBuilder().build(
                historical_reference_frame,
                as_of_date=decision_as_of_date,
                minimum_sample_size=minimum_cohort_sample_size,
            )
            ranking_result = PromotionArchetypeRanker().rank(
                cohort_history.archetype_history_frame,
                minimum_sample_size=minimum_cohort_sample_size,
            )
            if operator_progress is not None:
                operator_progress.update_heartbeat(
                    subtask="running cohort backtest and writing cohort report package"
                )
            try:
                backtest_result = PromotionCohortBacktester().backtest(
                    historical_reference_frame,
                    as_of_date=decision_as_of_date,
                    minimum_sample_size=minimum_cohort_sample_size,
                    similarity_threshold=similarity_seed_threshold,
                )
            except ValueError:
                backtest_result = None
            if backtest_result is not None:
                cohort_report_artifacts = PromotionCohortReportBuilder().write_reports(
                    run_id=run_id,
                    cohort_history=cohort_history,
                    backtest_result=backtest_result,
                    ranking_result=ranking_result,
                    artifact_paths=artifact_paths,
                )
        except ValueError:
            cohort_history = None

        if operator_progress is not None:
            operator_progress.update_heartbeat(
                subtask="calibrating thresholds, fusing row and cohort evidence, and running diagnostics"
            )
        decision_input_frame = _build_decision_input_frame(
            scored_frame=assigned_evaluation_frame,
            cohort_history=cohort_history,
            backtest_result=backtest_result if use_backtest_matches_for_evaluation else None,
            ranking_result=ranking_result,
            as_of_date=decision_as_of_date,
            minimum_cohort_sample_size=minimum_cohort_sample_size,
            similarity_threshold=similarity_seed_threshold,
        )
        calibration_input_frame = decision_input_frame
        if cohort_history is not None:
            calibration_input_frame = _build_decision_input_frame(
                scored_frame=cohort_history.assigned_frame,
                cohort_history=cohort_history,
                backtest_result=backtest_result,
                ranking_result=ranking_result,
                as_of_date=decision_as_of_date,
                minimum_cohort_sample_size=minimum_cohort_sample_size,
                similarity_threshold=similarity_seed_threshold,
            )
        calibration_result = PromotionDecisionCalibrator().calibrate(
            calibration_input_frame,
            minimum_sample_size=minimum_cohort_sample_size,
        )
        thresholds_used = _resolve_thresholds(
            calibration_thresholds=calibration_result.thresholds,
            similarity_threshold=similarity_threshold,
            archetype_confidence_floor=archetype_confidence_floor,
            row_model_confidence_floor=row_model_confidence_floor,
        )
        decision_fusion = PromotionDecisionFusion().fuse(
            decision_input_frame,
            config=PromotionDecisionFusionConfig.from_thresholds(thresholds_used),
        )
        diagnostics_result = PromotionDecisionDiagnostics().analyze(
            decision_fusion.decision_surface_frame,
            low_confidence_floor=max(
                float(thresholds_used["row_model_confidence_floor"]),
                float(thresholds_used["archetype_confidence_floor"]),
            ),
            disagreement_cutoff=float(
                thresholds_used["disagreement_penalty_cutoffs"]["moderate"]
            ),
        )

        if operator_progress is not None:
            operator_progress.update_heartbeat(
                subtask="writing decision-surface tables, diagnostics, and calibration manifests"
            )
        run_root = artifact_paths.decision_surface_run_root(run_id)
        run_root.mkdir(parents=True, exist_ok=True)
        calibration_summary_path = artifact_paths.decision_surface_calibration_summary_path(run_id)
        calibration_summary_path.parent.mkdir(parents=True, exist_ok=True)
        calibration_summary_path.write_text(
            json.dumps(calibration_result.summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        calibration_thresholds_path = artifact_paths.decision_surface_calibration_thresholds_path(
            run_id
        )
        calibration_thresholds_path.parent.mkdir(parents=True, exist_ok=True)
        calibration_thresholds_path.write_text(
            json.dumps(thresholds_used, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        metrics_payload = {
            **decision_fusion.metrics,
            "diagnostics": diagnostics_result.summary,
        }
        dataset_feature_columns = _manifest_string_tuple(
            resolved_dataset_artifact.manifest.get("feature_columns")
        )
        dataset_target_columns = _manifest_string_tuple(
            resolved_dataset_artifact.manifest.get("target_columns")
        )
        reporting_artifacts = PromotionDecisionSurfaceReportBuilder().write_reports(
            run_id=run_id,
            decision_surface_frame=decision_fusion.decision_surface_frame,
            diagnostics_result=diagnostics_result,
            metrics=metrics_payload,
            disagreement_cutoff=float(
                thresholds_used["disagreement_penalty_cutoffs"]["moderate"]
            ),
            artifact_paths=artifact_paths,
            manifest_payload={
                "run_id": run_id,
                "decision_surface_version": PROMOTION_DECISION_SURFACE_VERSION,
                "as_of_date": str(decision_as_of_date),
                "dataset_path": resolved_dataset_artifact.dataset_path,
                "dataset_manifest_path": resolved_dataset_artifact.dataset_manifest_path,
                "dataset_run_id": resolved_dataset_artifact.run_id,
                "dataset_created_at": resolved_dataset_artifact.created_at_utc,
                "dataset_schema_version": _dataset_manifest_value(
                    resolved_dataset_artifact.manifest,
                    "schema_version",
                ),
                "dataset_version": _dataset_manifest_value(
                    resolved_dataset_artifact.manifest,
                    "dataset_version",
                ),
                "model_bundle_path": resolved_model_bundle.model_bundle_path,
                "model_manifest_path": resolved_model_bundle.model_manifest_path,
                "model_inference_schema_path": resolved_model_bundle.inference_schema_path,
                "model_run_id": resolved_model_bundle.run_id,
                "model_created_at": resolved_model_bundle.created_at_utc,
                "cohort_history_path": cohort_report_artifacts.manifest_path if cohort_report_artifacts else None,
                "cohort_report_manifest_path": cohort_report_artifacts.manifest_path if cohort_report_artifacts else None,
                "calibration_summary_path": str(calibration_summary_path),
                "calibration_thresholds_path": str(calibration_thresholds_path),
                "feature_column_count": len(dataset_feature_columns) if dataset_feature_columns is not None else evaluation_feature_column_count,
                "target_column_count": len(dataset_target_columns) if dataset_target_columns is not None else None,
                "modeled_target_column_count": compatibility_result.model_target_column_count,
                "artifact_compatibility": compatibility_result.to_dict(),
                "inspection_package_paths": None,
                "row_count": int(len(decision_fusion.decision_surface_frame.index)),
                "thresholds_used": thresholds_used,
            },
        )
    if (
        operator_progress is not None
        and decision_surface_stage_number is not None
        and total_stages is not None
    ):
        operator_progress.complete_stage(
            row_count=int(len(decision_fusion.decision_surface_frame.index)),
            file_count=sum(len(paths) for paths in reporting_artifacts.report_paths.values()) + 5,
            output_paths=(
                artifact_paths.decision_surface_run_root(run_id),
                reporting_artifacts.manifest_path,
            ),
            note="Decision surface tables, diagnostics, calibration, and manifest persisted.",
        )
    if (
        operator_progress is not None
        and inspection_stage_number is not None
        and total_stages is not None
    ):
        operator_progress.start_stage(
            inspection_stage_number,
            total_stages,
            "Build inspection/review outputs",
        )
        operator_progress.detail(
            "action: write the inspection review packet, rollups, and execution summary"
        )
    inspection_context = (
        operator_progress.heartbeat(
            "writing inspection/review outputs and execution summary",
            heartbeat_seconds=10.0,
            row_count=int(len(decision_fusion.decision_surface_frame.index)),
        )
        if operator_progress is not None
        else nullcontext()
    )
    with inspection_context:
        inspection_artifacts = PromotionDecisionSurfaceInspectionBuilder().write_reports(
            run_id=run_id,
            decision_surface_frame=decision_fusion.decision_surface_frame,
            calibration_summary=calibration_result.summary,
            thresholds_used=thresholds_used,
            diagnostics_summary=diagnostics_result.summary,
            artifact_paths=artifact_paths,
        )
        decision_surface_manifest_payload = json.loads(
            Path(reporting_artifacts.manifest_path).read_text(encoding="utf-8")
        )
        decision_surface_manifest_payload["inspection_package_paths"] = {
            "manifest_path": inspection_artifacts.manifest_path,
            "report_paths": inspection_artifacts.report_paths,
        }
        Path(reporting_artifacts.manifest_path).write_text(
            json.dumps(decision_surface_manifest_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        execution_summary_path = artifact_paths.decision_surface_execution_summary_path(run_id)
        execution_summary_path.parent.mkdir(parents=True, exist_ok=True)
        execution_summary_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "executed_at_utc": datetime.now(tz=UTC).isoformat(),
                    "decision_surface_version": PROMOTION_DECISION_SURFACE_VERSION,
                    "dataset_artifact": {
                        "path": resolved_dataset_artifact.dataset_path,
                        "manifest_path": resolved_dataset_artifact.dataset_manifest_path,
                        "run_id": resolved_dataset_artifact.run_id,
                        "created_at": resolved_dataset_artifact.created_at_utc,
                    },
                    "model_artifact": {
                        "bundle_path": resolved_model_bundle.model_bundle_path,
                        "manifest_path": resolved_model_bundle.model_manifest_path,
                        "inference_schema_path": resolved_model_bundle.inference_schema_path,
                        "run_id": resolved_model_bundle.run_id,
                        "created_at": resolved_model_bundle.created_at_utc,
                    },
                    "artifact_compatibility": compatibility_result.to_dict(),
                    "decision_surface_manifest_path": reporting_artifacts.manifest_path,
                    "decision_surface_metrics_path": reporting_artifacts.metrics_path,
                    "diagnostics_summary_path": reporting_artifacts.diagnostics_summary_path,
                    "inspection_manifest_path": inspection_artifacts.manifest_path,
                    "cohort_report_manifest_path": cohort_report_artifacts.manifest_path if cohort_report_artifacts else None,
                    "calibration_summary_path": str(calibration_summary_path),
                    "calibration_thresholds_path": str(calibration_thresholds_path),
                    "row_count": int(len(decision_fusion.decision_surface_frame.index)),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    if (
        operator_progress is not None
        and inspection_stage_number is not None
        and total_stages is not None
    ):
        operator_progress.complete_stage(
            row_count=int(len(decision_fusion.decision_surface_frame.index)),
            file_count=sum(len(paths) for paths in inspection_artifacts.report_paths.values()) + 2,
            output_paths=(
                artifact_paths.inspection_run_root(run_id),
                inspection_artifacts.manifest_path,
                execution_summary_path,
            ),
            note="Commercial inspection packet and execution summary persisted.",
        )
    return PromotionDecisionSurfaceRunArtifacts(
        decision_surface_manifest_path=reporting_artifacts.manifest_path,
        decision_surface_metrics_path=reporting_artifacts.metrics_path,
        diagnostics_summary_path=reporting_artifacts.diagnostics_summary_path,
        calibration_summary_path=str(calibration_summary_path),
        calibration_thresholds_path=str(calibration_thresholds_path),
        execution_summary_path=str(execution_summary_path),
        inspection_manifest_path=inspection_artifacts.manifest_path,
        report_paths=reporting_artifacts.report_paths,
        inspection_report_paths=inspection_artifacts.report_paths,
        cohort_report_manifest_path=cohort_report_artifacts.manifest_path if cohort_report_artifacts else None,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the governed promotions decision surface.")
    parser.add_argument("--dataset-path")
    parser.add_argument("--dataset-run-id")
    parser.add_argument("--model-bundle-path")
    parser.add_argument("--model-run-id")
    parser.add_argument("--artifact-root")
    parser.add_argument(
        "--run-id",
        default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    parser.add_argument("--as-of-date")
    parser.add_argument("--minimum-cohort-sample-size", type=int, default=3)
    parser.add_argument("--similarity-threshold", type=float)
    parser.add_argument("--archetype-confidence-floor", type=float)
    parser.add_argument("--row-model-confidence-floor", type=float)
    return parser


def _build_decision_input_frame(
    *,
    scored_frame: pd.DataFrame,
    cohort_history,
    backtest_result: PromotionCohortBacktestResult | None,
    ranking_result: PromotionArchetypeRankingResult,
    as_of_date: date,
    minimum_cohort_sample_size: int,
    similarity_threshold: float,
) -> pd.DataFrame:
    match_frame = empty_cohort_match_frame(scored_frame)
    if backtest_result is not None and not backtest_result.row_matches_frame.empty:
        backtest_matches = backtest_result.row_matches_frame.loc[
            :, [column_name for column_name in match_frame.columns if column_name in backtest_result.row_matches_frame.columns]
        ].drop_duplicates(subset=["promotion_row_key"])
        match_frame = match_frame.drop(columns=[column_name for column_name in backtest_matches.columns if column_name != "promotion_row_key"]).merge(
            backtest_matches,
            on="promotion_row_key",
            how="left",
        )
        fallback_frame = empty_cohort_match_frame(scored_frame)
        for column_name in fallback_frame.columns:
            if column_name == "promotion_row_key":
                continue
            match_frame[column_name] = match_frame[column_name].where(match_frame[column_name].notna(), fallback_frame[column_name])
    if cohort_history is not None and not cohort_history.archetype_history_frame.empty:
        scored_keys = set(match_frame.loc[match_frame["nearest_archetype_key"].astype(str).str.len() > 0, "promotion_row_key"].tolist())
        promo_start = pd.to_datetime(scored_frame.get("promotion_start_date_date"), errors="coerce")
        promo_end = pd.to_datetime(scored_frame.get("promotional_end_date_date"), errors="coerce")
        future_like_mask = (promo_start >= pd.Timestamp(as_of_date)) | (promo_end > pd.Timestamp(as_of_date))
        rows_to_score = scored_frame.loc[
            future_like_mask & ~scored_frame["promotion_row_key"].isin(scored_keys)
        ].copy()
        if not rows_to_score.empty:
            direct_matches = PromotionCohortSimilarity().score(
                rows_to_score,
                cohort_history.archetype_history_frame,
                config=CohortSimilarityConfig(
                    minimum_sample_size=minimum_cohort_sample_size,
                    similarity_threshold=similarity_threshold,
                ),
            )
            direct_matches = direct_matches.drop_duplicates(subset=["promotion_row_key"])
            match_frame = match_frame.drop(columns=[column_name for column_name in direct_matches.columns if column_name != "promotion_row_key"]).merge(
                direct_matches,
                on="promotion_row_key",
                how="left",
            )
            fallback_frame = empty_cohort_match_frame(scored_frame)
            for column_name in fallback_frame.columns:
                if column_name == "promotion_row_key":
                    continue
                match_frame[column_name] = match_frame[column_name].where(match_frame[column_name].notna(), fallback_frame[column_name])
    decision_input = scored_frame.merge(match_frame, on="promotion_row_key", how="left")
    if ranking_result.rankings_frame.empty:
        return decision_input
    ranking_lookup = ranking_result.rankings_frame.loc[
        :, [
            "cohort_family",
            "cohort_key",
            "archetype_strength_score",
            "archetype_destructiveness_score",
            "archetype_fragility_score",
            "archetype_repeatability_score",
            "archetype_confidence_score",
        ]
    ].rename(
        columns={
            "cohort_family": "nearest_archetype_family",
            "cohort_key": "nearest_archetype_key",
            "archetype_strength_score": "nearest_archetype_strength_score",
            "archetype_destructiveness_score": "nearest_archetype_destructiveness_score",
            "archetype_fragility_score": "nearest_archetype_fragility_score",
            "archetype_repeatability_score": "nearest_archetype_repeatability_score",
            "archetype_confidence_score": "nearest_archetype_confidence_score",
        }
    )
    return decision_input.merge(ranking_lookup, on=["nearest_archetype_family", "nearest_archetype_key"], how="left")


def _resolve_thresholds(
    *,
    calibration_thresholds: dict[str, object],
    similarity_threshold: float | None,
    archetype_confidence_floor: float | None,
    row_model_confidence_floor: float | None,
) -> dict[str, object]:
    resolved = dict(calibration_thresholds)
    resolved["similarity_threshold"] = float(
        similarity_threshold
        if similarity_threshold is not None
        else calibration_thresholds.get("similarity_threshold_suggestion", 0.55)
    )
    resolved["archetype_confidence_floor"] = float(
        archetype_confidence_floor
        if archetype_confidence_floor is not None
        else calibration_thresholds.get("archetype_confidence_floor_suggestion", 0.45)
    )
    resolved["row_model_confidence_floor"] = float(
        row_model_confidence_floor
        if row_model_confidence_floor is not None
        else calibration_thresholds.get("row_model_confidence_floor_suggestion", 0.45)
    )
    return resolved


def _dataset_manifest_value(dataset_manifest: dict[str, object] | None, key: str) -> object | None:
    if not dataset_manifest:
        return None
    return dataset_manifest.get(key)


def _manifest_string_tuple(raw_value: object) -> tuple[str, ...] | None:
    if raw_value is None or not isinstance(raw_value, (list, tuple)):
        return None
    return tuple(str(value) for value in raw_value)


if __name__ == "__main__":
    main()