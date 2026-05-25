from __future__ import annotations

"""Operational promotions runtime that composes extract, train, score, and decision-surface runs."""

from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
import argparse
from collections.abc import Callable
import csv
import json
import logging
from pathlib import Path
import sys

import pandas as pd

from data.promotions.chunked_extraction_writer import (
    PromotionChunkedExtractionWriter,
    PromotionInvalidResumeStateError,
)
from data.promotions.extracted_dataset_writer import PromotionExtractionWriter
from data.promotions.partition_rollup_validator import (
    PartitionRollupValidationError,
    validate_partition_completion_for_rollup,
)
from data.promotions.mssql_query_executor import (
    PromotionMssqlQueryError,
    PromotionMssqlQueryTimeoutError,
    SqlAlchemyMssqlQueryExecutor,
)
from data.promotions.promotion_base_extractor import (
    PromotionBaseExtractor,
    PromotionExtractionManifest,
    PromotionExtractionPreflightResult,
    PromotionExtractionTelemetry,
    write_extraction_observability,
)
from data.promotions.sql import PromotionBaseQueryOptions
from models.promotions.trainer import (
    PROMOTION_TRAINER_TARGET_MODE_CHOICES,
    PromotionModelTrainer,
    _resolve_promotion_trainer_target_mode,
)
from runtime.promotions.config import (
    PromotionArtifactPaths,
    PromotionCompletedExtractionRuntimeSettings,
    PromotionCompletedPartitionSettings,
    PromotionCompletedPreflightPlannerSettings,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from runtime.promotions.completed_extraction_batches import (
    execute_completed_partition_landed_batches,
    load_existing_finalized_partition_artifact,
)
from runtime.promotions.local_inspection import (
    PromotionLocalInspectionArtifacts,
    write_local_inspection_outputs,
)
from runtime.promotions.nas_bootstrap import (
    PromotionNasBootstrapArtifacts,
    bootstrap_promotions_nas,
    validate_governed_nas_root,
)
from runtime.promotions.operator_progress import (
    PromotionOperatorProgress,
    PromotionOperatorProgressArtifacts,
    PromotionOperatorStageRecord,
)
from runtime.promotions.audit_promotions_operational_cycle import audit_operational_cycle
from runtime.promotions.promotion_demand_backtest_orchestrator import (
    PromotionBacktestArtifactPaths,
    PromotionBacktestOrchestratorError,
    write_completed_promotion_demand_backtest,
)
from runtime.promotions.commercial_outcome import (
    COMMERCIAL_FAILURE_RUNTIME,
    CommercialOutcomeInput,
    PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
    build_publication_freshness_diagnostic as build_commercial_outcome_freshness_diagnostic,
    classify_commercial_outcome,
    classify_stage13_validation_skip,
)
from runtime.promotions.commercial_delta import build_commercial_delta_intelligence
from runtime.promotions.commercial_change_explainer import (
    build_commercial_change_explainability_artifacts,
)
from runtime.promotions.commercial_outcome_attribution import (
    build_commercial_outcome_attribution_artifacts,
)
from runtime.promotions.commercial_policy_calibration import (
    build_commercial_policy_calibration_artifacts,
)
from runtime.promotions.commercial_policy_simulator import (
    build_commercial_policy_simulation_artifacts,
)
from runtime.promotions.commercial_action_instructions import (
    build_commercial_action_instruction_artifacts,
)
from runtime.promotions.commercial_publishability_split import (
    build_commercial_publishability_split,
    split_to_manifest_payload,
)
from runtime.promotions.publication_opportunity import (
    PublicationOpportunityInput,
    build_commercial_operator_brief,
    build_commercial_stage_timing,
    build_duplicate_registry_skip_summary,
    build_publish_reconciliation_summary,
    build_publication_freshness_diagnostic,
    classify_publication_opportunity,
    classify_commercial_freshness,
    classify_replay_safety,
    validate_freshness_replay_consistency,
)
from runtime.promotions.run_promotions_decision_surface import (
    run_decision_surface_for_scored_rows,
)
from runtime.promotions.scoring_service import PromotionModelScorer
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler
from state.promotions.datasets.stage4_performance_recorder import (
    Stage4PerformanceRecorder,
)
from state.promotions.datasets.dataset_validators import NegativeStockPosturePolicy
from state.promotions.feature_engineering import PromotionFeatureEngineer
from state.promotions.targets import PromotionTargetEngineer
from surfaces.promotions.reporting.report_builder import PromotionReportBuilder
from surfaces.promotions.reporting.store_prediction_download_builder import (
    PromotionStorePredictionDownloadBuilder,
)
from surfaces.promotions.reporting.store_prediction_publisher import (
    PromotionStoreExecutionPublishArtifacts,
    StorePredictionPublisher,
)
from surfaces.promotions.reporting.pilot_validation import (
    PromotionPilotValidationService,
)


LOGGER = logging.getLogger(__name__)
OPERATIONAL_CYCLE_STAGE_COUNT = 14
COMPLETED_EXTRACTION_STAGE_NAME = "Extract completed promotions"
ZERO_FUTURE_SCORED_ROWS_SKIP_CLASS = "ZERO_FUTURE_SCORED_ROWS"
ZERO_FUTURE_SCORED_ROWS_REASON = "zero_future_scored_rows"
ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER = "unavailable_zero_future_scored_rows_noop"
ZERO_FUTURE_SCORED_ROWS_SKIPPED_STAGE_NUMBERS = (8, 9, 10, 11, 12, 13, 14)
FULL_COMPLETED_SCOPE_STRATEGY = "full_completed_scope"
COMPLETED_PROOF_SLICE_DATE_COUNT = 3
VALID_COMPLETED_PARTITION_STRATEGIES = frozenset(
    {
        "store_number",
        "supplier_number",
        "store_sku_hash_bucket",
        "promotion_name_hash_bucket",
        "promotion_row_key_hash_bucket",
    }
)


class PromotionCompletedPreflightRejectedError(RuntimeError):
    """Raised when completed preflight planning rejects extraction before heavy SQL runs."""


class PromotionCompletedExtractionInterruptedError(RuntimeError):
    """Raised when Stage 3 completed extraction is interrupted by operator cancellation."""


@dataclass(frozen=True)
class PromotionOperationalCycleExtractionArtifacts:
    selection_mode: str
    frame: pd.DataFrame
    base_path: str
    manifest_path: str
    rendered_sql_path: str | None
    rendered_sql_parameters_path: str | None
    telemetry_json_path: str | None
    telemetry_csv_path: str | None
    diagnostics_summary_json_path: str | None
    diagnostics_summary_txt_path: str | None
    candidate_promotion_row_count: int | None
    manifest: dict[str, object]
    extraction_mode: str = "live_sql"
    partition_strategy: str | None = None
    partition_count: int | None = None
    partition_index: int | None = None
    fetch_mode: str = "full_fetch"
    chunk_mode: str = "full_fetch"
    chunk_count: int = 0
    completed_chunk_count: int = 0
    cumulative_rows_written: int = 0
    batch_count: int = 0
    finalized_batch_count: int = 0
    resumed_batch_count: int = 0
    rebuilt_batch_count: int = 0
    total_landed_rows: int = 0
    completion_state: str | None = None
    partition_completion_state: str | None = None
    resume_state: str | None = None
    skipped_due_to_existing_completion: bool = False
    partition_progress_path: str | None = None
    partition_completion_marker_path: str | None = None
    partition_summary_path: str | None = None
    preflight_summary_json_path: str | None = None
    preflight_summary_csv_path: str | None = None
    rendered_preflight_sql_path: str | None = None
    rendered_preflight_sql_parameters_path: str | None = None
    preflight_verdict: str | None = None
    preflight_reason: str | None = None
    estimated_cost_score: float | None = None
    estimated_extract_query_seconds: float | None = None
    fixed_overhead_seconds: float | None = None
    variable_cost_signal: float | None = None
    cost_model_version: str | None = None
    cost_guardrail_verdict: str | None = None
    cost_guardrail_reason: str | None = None
    recommended_partition_strategy: str | None = None
    recommended_partition_count: int | None = None
    completed_preflight_cost_diagnostic_path: str | None = None
    completed_preflight_model_learning_diagnostic_path: str | None = None
    completed_proof_fallback_used: bool = False
    completed_proof_fallback_mode: str | None = None
    completed_proof_fallback_reason: str | None = None


@dataclass(frozen=True)
class PromotionOperationalCycleArtifacts:
    manifest_path: str
    nas_bootstrap_summary_path: str
    nas_root: str
    local_inspection_root: str | None
    completed_base_path: str
    completed_base_manifest_path: str
    completed_partition_summary_path: str | None
    future_base_path: str
    future_base_manifest_path: str
    dataset_path: str
    dataset_manifest_path: str
    model_manifest_path: str
    scoring_manifest_path: str
    score_report_manifest_path: str
    decision_surface_manifest_path: str
    decision_surface_execution_summary_path: str
    decision_surface_inspection_manifest_path: str
    inspection_review_packet_csv_path: str
    store_prediction_master_csv_path: str
    store_prediction_download_path: str
    store_prediction_per_store_csv_paths: tuple[str, ...]
    store_prediction_per_store_promotion_csv_paths: tuple[str, ...]
    store_prediction_reconciliation_csv_path: str
    store_prediction_manifest_path: str
    store_prediction_manifest_csv_path: str
    commercial_prediction_registry_path: str
    commercial_prediction_manifest_paths: tuple[str, ...]
    commercial_pos_upload_paths: tuple[str, ...]
    commercial_review_paths: tuple[str, ...]
    commercial_summary_paths: tuple[str, ...]
    commercial_reconciliation_paths: tuple[str, ...]
    commercial_publication_summary_path: str
    commercial_diagnostics_paths: tuple[str, ...]
    commercial_skipped_paths: tuple[str, ...]
    pilot_validation_summary_csv_path: str
    pilot_validation_summary_json_path: str
    pilot_validation_failures_csv_path: str
    gold_standard_acceptance_results_csv_path: str
    gold_standard_acceptance_results_json_path: str
    validation_manifest_path: str
    validation_skip_summary_path: str
    commercial_run_outcome_summary_path: str
    publication_freshness_diagnostic_path: str
    commercial_delta_summary_path: str
    commercial_delta_top_changes_csv_path: str
    commercial_delta_store_summary_csv_path: str
    commercial_change_explanations_csv_path: str
    commercial_priority_queue_csv_path: str
    commercial_action_summary_path: str
    commercial_outcome_attribution_csv_path: str
    recommendation_effectiveness_summary_path: str
    recommendation_effectiveness_by_reason_csv_path: str
    recommendation_learning_priority_queue_csv_path: str
    commercial_policy_calibration_summary_path: str
    commercial_policy_calibration_by_segment_csv_path: str
    commercial_policy_watchlist_csv_path: str
    commercial_policy_calibration_brief_path: str
    commercial_policy_simulation_summary_path: str
    commercial_policy_simulation_by_segment_csv_path: str
    commercial_policy_simulation_watchlist_csv_path: str
    commercial_policy_simulation_brief_path: str
    commercial_action_instruction_summary_path: str
    commercial_action_priority_queue_csv_path: str
    commercial_action_by_segment_csv_path: str
    commercial_action_instruction_brief_path: str
    local_store_prediction_download_path: str | None
    local_decision_surface_csv_path: str | None
    local_review_packet_csv_path: str | None
    local_run_summary_path: str | None
    audit_manifest_path: str
    audit_summary_json_path: str
    audit_summary_csv_path: str
    operator_log_path: str
    operator_summary_path: str
    operator_summary_csv_path: str
    operator_stage_timings_path: str
    promotion_demand_backtest_csv_path: str | None = None
    promotion_demand_backtest_parquet_path: str | None = None
    promotion_demand_backtest_summary_path: str | None = None
    promotion_demand_backtest_by_segment_csv_path: str | None = None
    promotion_demand_backtest_watchlist_csv_path: str | None = None
    promotion_demand_backtest_brief_path: str | None = None
    promotion_demand_backtest_manifest_path: str | None = None
    promotion_demand_backtest_calibration_summary_path: str | None = None
    promotion_demand_backtest_calibration_brief_path: str | None = None


@dataclass(frozen=True)
class PromotionOperationalCycleManifest:
    run_id: str
    score_run_id: str
    decision_surface_run_id: str
    executed_at_utc: str
    as_of_date: str
    artifact_root: str
    nas_root: str
    local_inspection_root: str | None
    execution_mode: str
    runtime_settings: dict[str, object]
    completed_extraction: dict[str, object]
    training_dataset: dict[str, object]
    model_bundle: dict[str, object]
    future_extraction: dict[str, object]
    scoring: dict[str, object]
    decision_surface: dict[str, object]
    nas_bootstrap: dict[str, object] | None = None
    local_inspection: dict[str, object] | None = None
    store_outputs: dict[str, object] | None = None
    audit: dict[str, object] | None = None
    operator_progress: dict[str, object] | None = None
    final_outputs: dict[str, str] | None = None
    failure: dict[str, object] | None = None
    completed_promotions_demand_backtest: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionCompletedPartitionRetryRecord:
    run_id: str
    stage: str
    attempt_number: int
    selection_mode: str
    initial_partition_strategy: str
    initial_partition_count: int | None
    recommended_partition_strategy: str | None
    recommended_partition_count: int | None
    accepted_strategy: str | None
    accepted_partition_count: int | None
    verdict: str
    reason: str
    failed_partition_index: int | None
    candidate_promotion_row_count: int | None
    candidate_store_sku_count: int | None
    candidate_window_count: int | None
    candidate_window_span_days_total: int | None
    candidate_window_span_days_max: int | None
    estimated_cost_score: float | None
    cost_guardrail_verdict: str | None
    cost_guardrail_reason: str | None
    status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _derive_stage12_legitimate_excluded_row_count(
    commercial_publish_artifacts: PromotionStoreExecutionPublishArtifacts,
) -> int:
    non_legitimate_excluded_count = (
        int(commercial_publish_artifacts.skipped_due_to_review_count)
        + int(commercial_publish_artifacts.skipped_due_to_schema_count)
        + int(commercial_publish_artifacts.skipped_due_to_mapping_count)
        + int(commercial_publish_artifacts.skipped_due_to_null_sku_count)
    )
    return max(
        int(commercial_publish_artifacts.pos_excluded_row_count) - non_legitimate_excluded_count,
        0,
    )


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = _build_settings(args)
    if settings.completed_preflight_planner.planner_only:
        if (
            settings.completed_partitioning is not None
            and settings.completed_partitioning.partition_index is None
        ):
            raise ValueError(
                "planner_only with partition_count but no partition_index is not supported by run_promotions_operational_cycle. Use inspect_promotions_sql_extraction for single-partition planner checks."
            )
        from runtime.promotions.inspect_promotions_sql_extraction import (
            inspect_sql_extraction,
            render_sql_inspection_report,
        )

        planner_summary = inspect_sql_extraction(
            settings=settings,
            run_id=args.run_id,
            selection_mode="completed",
            query_options=PromotionBaseQueryOptions(
                completed_partition=settings.completed_partitioning,
            ),
            run_preflight=True,
            planner_only=True,
        )
        render_sql_inspection_report(planner_summary, stream=sys.stdout)
        return
    artifacts = run_operational_cycle(
        settings=settings,
        run_id=args.run_id,
        score_run_id=args.score_run_id,
        decision_surface_run_id=args.decision_surface_run_id,
        target_mode=args.target_mode,
        minimum_cohort_sample_size=args.minimum_cohort_sample_size,
        similarity_threshold=args.similarity_threshold,
        archetype_confidence_floor=args.archetype_confidence_floor,
        row_model_confidence_floor=args.row_model_confidence_floor,
        proof_mode=getattr(args, "proof_mode", False),
        proof_stop_after_stage=getattr(args, "proof_stop_after_stage", None),
        proof_max_future_promotions=getattr(args, "proof_max_future_promotions", None),
        proof_future_fallback_mode=getattr(args, "proof_future_fallback_mode", None),
        proof_future_fallback_topn_limit=getattr(
            args,
            "proof_future_fallback_topn_limit",
            None,
        ),
        proof_future_fallback_slice_promotions=getattr(
            args,
            "proof_future_fallback_slice_promotions",
            None,
        ),
    )
    LOGGER.info(
        "Completed promotions operational cycle: manifest=%s decision_surface=%s",
        artifacts.manifest_path,
        artifacts.decision_surface_manifest_path,
    )


def run_operational_cycle(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    score_run_id: str | None = None,
    decision_surface_run_id: str | None = None,
    target_mode: str | None = None,
    minimum_cohort_sample_size: int = 3,
    similarity_threshold: float | None = None,
    archetype_confidence_floor: float | None = None,
    row_model_confidence_floor: float | None = None,
    execution_mode: str = "live_sql",
    extraction_provider: Callable[..., PromotionOperationalCycleExtractionArtifacts] | None = None,
    proof_mode: bool = False,
    proof_stop_after_stage: int | None = None,
    proof_max_future_promotions: int | None = None,
    proof_future_fallback_mode: str | None = None,
    proof_future_fallback_topn_limit: int | None = None,
    proof_future_fallback_slice_promotions: int | None = None,
) -> PromotionOperationalCycleArtifacts:
    """Run the governed promotions cycle from extraction through decision surface."""

    resolved_target_mode = _resolve_promotion_trainer_target_mode(target_mode)
    resolved_score_run_id = score_run_id or f"{run_id}-score"
    resolved_decision_surface_run_id = decision_surface_run_id or f"{run_id}-decision-surface"
    manifest_path = settings.artifacts.operational_cycle_manifest_path(run_id)
    progress = PromotionOperatorProgress(run_id=run_id, artifact_paths=settings.artifacts)
    extraction_runner = extraction_provider or _extract_promotions_base_artifact
    nas_bootstrap_artifacts: PromotionNasBootstrapArtifacts | None = None
    local_inspection_artifacts: PromotionLocalInspectionArtifacts | None = None
    manifest_payload: dict[str, object] | None = None
    requested_completed_partitioning = settings.completed_partitioning
    effective_completed_partitioning = requested_completed_partitioning
    completed_partition_retry_records: list[PromotionCompletedPartitionRetryRecord] = []
    completed_partition_retries_json_path = str(
        settings.artifacts.completed_partition_retries_json_path(run_id)
    )
    completed_partition_retries_csv_path = str(
        settings.artifacts.completed_partition_retries_csv_path(run_id)
    )
    stage6_guardrail_path: str | None = None
    stage6_plan_path: str | None = None
    stage6_failure_summary_path: str | None = None
    completed_preflight_cost_diagnostic_path: str | None = None
    completed_preflight_model_learning_diagnostic_path: str | None = None
    completed_proof_fallback_used = False
    completed_proof_fallback_mode: str | None = None
    completed_proof_fallback_reason: str | None = None
    can_persist_operator_outputs = False
    
    # Add helper for proof-mode stage-stop check
    def _should_stop_after_stage(stage_number: int) -> bool:
        return proof_stop_after_stage is not None and stage_number == proof_stop_after_stage
    
    progress.start_run(
        as_of_date=settings.as_of_date.isoformat(),
        artifact_root=settings.artifacts.root,
        local_inspection_root=settings.artifacts.local_inspection_root,
        server=settings.sql.server,
        database=settings.sql.database,
        execution_mode=execution_mode,
        connect_timeout_seconds=settings.sql.connect_timeout_seconds,
        connect_retry_attempts=settings.sql.connect_retry_attempts,
        connect_retry_backoff_seconds=settings.sql.connect_retry_backoff_seconds,
        query_timeout_seconds=settings.sql.query_timeout_seconds,
        partition_strategy=(
            settings.completed_partitioning.strategy
            if settings.completed_partitioning is not None
            else None
        ),
        partition_count=(
            requested_completed_partitioning.partition_count
            if requested_completed_partitioning is not None
            else None
        ),
        auto_repartition_completed=settings.completed_preflight_planner.auto_repartition_completed,
        max_completed_repartition_attempts=(
            settings.completed_preflight_planner.max_completed_repartition_attempts
        ),
        max_completed_partition_count=settings.completed_preflight_planner.max_completed_partition_count,
        enable_landed_batches=settings.completed_extraction_runtime.enable_landed_batches,
        batch_row_count=settings.completed_extraction_runtime.batch_row_count,
        completed_sales_history_start_date=(
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
        ),
        enable_chunked_fetch=settings.completed_extraction_runtime.enable_chunked_fetch,
        chunk_row_count=settings.completed_extraction_runtime.chunk_row_count,
        resume_completed_partitions=(
            settings.completed_extraction_runtime.resume_completed_partitions
        ),
        stage_temp_chunk_files=settings.completed_extraction_runtime.stage_temp_chunk_files,
        sql_settings_summary=settings.sql.safe_summary(),
    )
    try:
        progress.start_stage(1, OPERATIONAL_CYCLE_STAGE_COUNT, "Load runtime config")
        progress.detail("action: resolve runtime settings, run identifiers, and output roots")
        progress.detail(f"execution_mode: {execution_mode}")
        progress.detail(f"training_run_id: {run_id}")
        progress.detail(f"score_run_id: {resolved_score_run_id}")
        progress.detail(f"decision_surface_run_id: {resolved_decision_surface_run_id}")
        progress.detail(f"training_target_mode: {resolved_target_mode}")
        progress.detail(
            "completed_landed_batches: "
            f"{str(settings.completed_extraction_runtime.enable_landed_batches).lower()}"
        )
        progress.detail(
            f"completed_batch_row_count: {settings.completed_extraction_runtime.batch_row_count}"
        )
        progress.detail(
            "completed_chunked_fetch: "
            f"{str(settings.completed_extraction_runtime.enable_chunked_fetch).lower()}"
        )
        progress.detail(
            f"completed_chunk_row_count: {settings.completed_extraction_runtime.chunk_row_count}"
        )
        progress.detail(
            "resume_completed_partitions: "
            f"{str(settings.completed_extraction_runtime.resume_completed_partitions).lower()}"
        )
        progress.detail(
            "stage_temp_chunk_files: "
            f"{str(settings.completed_extraction_runtime.stage_temp_chunk_files).lower()}"
        )
        progress.complete_stage(
            output_paths=(settings.artifacts.root,),
            note="Runtime settings resolved for this operational cycle.",
        )

        progress.start_stage(2, OPERATIONAL_CYCLE_STAGE_COUNT, "Bootstrap governed NAS folders")
        progress.detail("action: create or validate governed NAS folders and write the bootstrap summary")
        nas_bootstrap_artifacts = bootstrap_promotions_nas(
            run_id=run_id,
            artifact_paths=settings.artifacts,
        )
        for line in nas_bootstrap_artifacts.operator_lines():
            progress.detail(line)
        validated_roots = tuple(directory.path for directory in nas_bootstrap_artifacts.directories)
        can_persist_operator_outputs = True
        progress.complete_stage(
            file_count=len(validated_roots) + 1,
            output_paths=(settings.artifacts.root, nas_bootstrap_artifacts.summary_path),
            note="Governed NAS folders are present, writable, and ready for this run.",
        )

        progress.start_stage(3, OPERATIONAL_CYCLE_STAGE_COUNT, "Extract completed promotions")
        if effective_completed_partitioning is not None and effective_completed_partitioning.partition_index is not None:
            raise ValueError(
                "partition_index is not supported by run_promotions_operational_cycle because the full completed set must be materialized before downstream stages. Use inspect_promotions_sql_extraction for single-partition runs."
            )
        completed_partition_retries_json_path, completed_partition_retries_csv_path = (
            _write_completed_partition_retry_history(
                settings=settings,
                run_id=run_id,
                requested_partition_settings=requested_completed_partitioning,
                active_partition_settings=effective_completed_partitioning,
                retry_records=completed_partition_retry_records,
                planner_settings=settings.completed_preflight_planner,
            )
        )
        progress.detail(
            f"completed_partition_retries_json_path: {completed_partition_retries_json_path}"
        )
        progress.detail(
            f"completed_partition_retries_csv_path: {completed_partition_retries_csv_path}"
        )
        should_run_completed_preflight = execution_mode == "live_sql"
        while True:
            completed_stage_message = _completed_stage_message(
                partition_settings=effective_completed_partitioning,
                execution_mode=execution_mode,
            )
            progress.detail(f"action: {completed_stage_message}")
            progress.detail(
                f"active_partition_strategy: {_partition_strategy_label(effective_completed_partitioning)}"
            )
            progress.detail(
                "active_partition_count: "
                f"{_partition_count_label(effective_completed_partitioning)}"
            )
            progress.detail(
                "repartition_attempt_number: "
                f"{_accepted_completed_repartition_attempt_count(completed_partition_retry_records)}/"
                f"{settings.completed_preflight_planner.max_completed_repartition_attempts}"
            )
            completed_preflight: PromotionExtractionPreflightResult | None = None
            completed_query_options: PromotionBaseQueryOptions | None = None
            try:
                if effective_completed_partitioning is None and should_run_completed_preflight:
                    completed_preflight = _run_completed_preflight_probe(
                        settings=settings,
                        run_id=run_id,
                        query_options=None,
                    )
                    _emit_completed_preflight_summary(
                        progress=progress,
                        preflight_result=completed_preflight,
                    )
                    completed_preflight_cost_diagnostic_path = (
                        _write_completed_preflight_cost_diagnostic(
                            settings=settings,
                            run_id=run_id,
                            preflight_result=completed_preflight,
                            rejection_reason=(
                                completed_preflight.summary.reason
                                if completed_preflight.summary.verdict != "SAFE_TO_EXTRACT"
                                else None
                            ),
                            proof_fallback_used=False,
                            proof_fallback_mode=None,
                        )
                    )
                    if completed_preflight.summary.verdict != "SAFE_TO_EXTRACT":
                        fallback_query_options, fallback_mode, fallback_reason = (
                            _resolve_completed_preflight_proof_fallback(
                                proof_mode=proof_mode,
                                planner_settings=settings.completed_preflight_planner,
                                preflight_result=completed_preflight,
                            )
                        )
                        if fallback_query_options is None:
                            _raise_for_completed_preflight_verdict(
                                preflight_result=completed_preflight,
                                selection_mode="completed",
                                as_of_date=settings.as_of_date.isoformat(),
                            )
                        completed_query_options = fallback_query_options
                        completed_proof_fallback_used = True
                        completed_proof_fallback_mode = fallback_mode
                        completed_proof_fallback_reason = fallback_reason
                        completed_preflight_cost_diagnostic_path = (
                            _write_completed_preflight_cost_diagnostic(
                                settings=settings,
                                run_id=run_id,
                                preflight_result=completed_preflight,
                                rejection_reason=completed_preflight.summary.reason,
                                proof_fallback_used=True,
                                proof_fallback_mode=fallback_mode,
                            )
                        )
                        progress.detail("proof_completed_fallback_used: true")
                        progress.detail(
                            f"proof_completed_fallback_mode: {fallback_mode}"
                        )
                        progress.detail(
                            f"proof_completed_fallback_reason: {fallback_reason}"
                        )
                with progress.heartbeat(
                    completed_stage_message,
                    heartbeat_seconds=8.0,
                ):
                    if effective_completed_partitioning is None:
                        completed_extraction = extraction_runner(
                            settings=settings,
                            run_id=run_id,
                            selection_mode="completed",
                            progress_callback=lambda subtask: progress.update_heartbeat(
                                subtask=subtask,
                                emit_now=True,
                            ),
                            query_options=completed_query_options,
                        )
                        if completed_preflight is not None:
                            completed_extraction = _with_preflight_artifacts(
                                extraction_artifact=completed_extraction,
                                preflight_result=completed_preflight,
                            )
                            completed_extraction = replace(
                                completed_extraction,
                                completed_preflight_cost_diagnostic_path=(
                                    completed_preflight_cost_diagnostic_path
                                ),
                                completed_proof_fallback_used=completed_proof_fallback_used,
                                completed_proof_fallback_mode=completed_proof_fallback_mode,
                                completed_proof_fallback_reason=completed_proof_fallback_reason,
                            )
                    else:
                        completed_extraction = _extract_completed_promotions_partitioned_artifact(
                            settings=settings,
                            run_id=run_id,
                            partition_settings=effective_completed_partitioning,
                            extraction_runner=extraction_runner,
                            progress=progress,
                            run_preflight=should_run_completed_preflight,
                        )
                break
            except BaseException as raw_error:
                if isinstance(raw_error, (SystemExit, GeneratorExit)):
                    raise
                error = _normalize_stage3_completed_extraction_error(
                    error=raw_error,
                    settings=settings,
                    run_id=run_id,
                    partition_settings=effective_completed_partitioning,
                )
                if completed_preflight_cost_diagnostic_path is not None:
                    setattr(
                        error,
                        "completed_preflight_cost_diagnostic_path",
                        completed_preflight_cost_diagnostic_path,
                    )
                setattr(error, "completed_proof_fallback_used", completed_proof_fallback_used)
                setattr(error, "completed_proof_fallback_mode", completed_proof_fallback_mode)
                setattr(error, "completed_proof_fallback_reason", completed_proof_fallback_reason)
                if getattr(error, "completed_partition_summary_path", None) is None:
                    setattr(
                        error,
                        "completed_partition_summary_path",
                        _write_completed_preflight_rejection_summary(
                            settings=settings,
                            run_id=run_id,
                            error=error,
                        ),
                    )
                _attach_completed_partition_retry_context(
                    error=error,
                    retry_records=completed_partition_retry_records,
                    retry_json_path=completed_partition_retries_json_path,
                    retry_csv_path=completed_partition_retries_csv_path,
                    planner_settings=settings.completed_preflight_planner,
                )
                if not isinstance(error, PromotionCompletedPreflightRejectedError):
                    _write_stage3_completed_extraction_failure_artifacts(
                        settings=settings,
                        run_id=run_id,
                        error=error,
                    )
                    if error is raw_error:
                        raise
                    raise error from raw_error
                next_partition_settings, retry_record, decision_reason = (
                    _resolve_completed_repartition_retry(
                        run_id=run_id,
                        current_partition_settings=effective_completed_partitioning,
                        error=error,
                        planner_settings=settings.completed_preflight_planner,
                        attempt_number=len(completed_partition_retry_records) + 1,
                    )
                )
                completed_partition_retry_records.append(retry_record)
                completed_partition_retries_json_path, completed_partition_retries_csv_path = (
                    _write_completed_partition_retry_history(
                        settings=settings,
                        run_id=run_id,
                        requested_partition_settings=requested_completed_partitioning,
                        active_partition_settings=effective_completed_partitioning,
                        retry_records=completed_partition_retry_records,
                        planner_settings=settings.completed_preflight_planner,
                    )
                )
                _attach_completed_partition_retry_context(
                    error=error,
                    retry_records=completed_partition_retry_records,
                    retry_json_path=completed_partition_retries_json_path,
                    retry_csv_path=completed_partition_retries_csv_path,
                    planner_settings=settings.completed_preflight_planner,
                )
                progress.detail(
                    f"repartition_attempt_number: {retry_record.attempt_number}"
                )
                progress.detail(
                    f"repartition_old_partition_strategy: {retry_record.initial_partition_strategy}"
                )
                progress.detail(
                    "repartition_old_partition_count: "
                    f"{retry_record.initial_partition_count if retry_record.initial_partition_count is not None else 'full_scope'}"
                )
                progress.detail(
                    "repartition_recommended_partition_strategy: "
                    f"{retry_record.recommended_partition_strategy or 'unavailable'}"
                )
                progress.detail(
                    "repartition_recommended_partition_count: "
                    f"{retry_record.recommended_partition_count if retry_record.recommended_partition_count is not None else 'unavailable'}"
                )
                progress.detail(f"repartition_decision: {retry_record.status}")
                progress.detail(f"repartition_decision_reason: {decision_reason}")
                if next_partition_settings is None:
                    error.args = (decision_reason,)
                    _write_stage3_completed_extraction_failure_artifacts(
                        settings=settings,
                        run_id=run_id,
                        error=error,
                    )
                    if error is raw_error:
                        raise
                    raise error from raw_error
                progress.detail(
                    f"accepted_partition_strategy: {next_partition_settings.strategy}"
                )
                progress.detail(
                    f"accepted_partition_count: {next_partition_settings.partition_count}"
                )
                effective_completed_partitioning = next_partition_settings
                progress.detail(
                    f"completed_partition_retries_json_path: {completed_partition_retries_json_path}"
                )
                progress.detail(
                    f"completed_partition_retries_csv_path: {completed_partition_retries_csv_path}"
                )
                progress.detail(
                    "repartition_status: continuing stage 3 with updated completed partitioning"
                )
        if effective_completed_partitioning is None:
            if completed_extraction.candidate_promotion_row_count is not None:
                progress.detail(
                    f"candidate_promotion_row_count: {completed_extraction.candidate_promotion_row_count}"
                )
        else:
            progress.detail(
                f"total_completed_candidate_rows: {completed_extraction.candidate_promotion_row_count or 0}"
            )
            progress.detail(
                f"total_extracted_rows: {int(completed_extraction.manifest.get('row_count', 0) or 0)}"
            )
            progress.detail(
                f"partitions_succeeded: {effective_completed_partitioning.partition_count}/{effective_completed_partitioning.partition_count}"
            )
            if completed_extraction.partition_summary_path is not None:
                progress.detail(
                    f"completed_partition_summary_path: {completed_extraction.partition_summary_path}"
                )
        progress.detail(
            f"completed_partition_retries_json_path: {completed_partition_retries_json_path}"
        )
        progress.detail(
            f"completed_partition_retries_csv_path: {completed_partition_retries_csv_path}"
        )
        if (
            completed_extraction.preflight_summary_json_path is not None
            and not completed_extraction.completed_proof_fallback_used
            and completed_extraction.extraction_mode == "live_sql"
            and effective_completed_partitioning is None
        ):
            completed_preflight_model_learning_diagnostic_path = (
                _write_completed_preflight_model_learning_diagnostic(
                    settings=settings,
                    run_id=run_id,
                    completed_extraction=completed_extraction,
                )
            )
            completed_extraction = replace(
                completed_extraction,
                completed_preflight_model_learning_diagnostic_path=(
                    completed_preflight_model_learning_diagnostic_path
                ),
            )
            progress.detail(
                "completed_preflight_model_learning_diagnostic_path: "
                f"{completed_preflight_model_learning_diagnostic_path}"
            )
        progress.complete_stage(
            row_count=int(completed_extraction.manifest.get("row_count", 0) or 0),
            file_count=(
                8
                if effective_completed_partitioning is None
                else 3 + (effective_completed_partitioning.partition_count * 8)
            ),
            output_paths=(
                completed_extraction.base_path,
                completed_extraction.manifest_path,
                *((completed_extraction.partition_summary_path,) if completed_extraction.partition_summary_path else ()),
                completed_partition_retries_json_path,
                completed_partition_retries_csv_path,
                *( 
                    (completed_extraction.rendered_sql_path,)
                    if completed_extraction.rendered_sql_path is not None
                    else ()
                ),
                *((completed_extraction.telemetry_json_path,) if completed_extraction.telemetry_json_path else ()),
                *((completed_extraction.diagnostics_summary_json_path,) if completed_extraction.diagnostics_summary_json_path else ()),
                *((completed_extraction.completed_preflight_cost_diagnostic_path,) if completed_extraction.completed_preflight_cost_diagnostic_path else ()),
                *((completed_extraction.completed_preflight_model_learning_diagnostic_path,) if completed_extraction.completed_preflight_model_learning_diagnostic_path else ()),
            ),
            note="Completed promotions base extract persisted.",
        )

        progress.start_stage(4, OPERATIONAL_CYCLE_STAGE_COUNT, "Build training dataset")
        progress.detail("action: engineer training targets and features, then assemble the governed dataset")
        stage4_recorder = Stage4PerformanceRecorder(run_id=run_id)
        with stage4_recorder.step("read_completed_base_parquet") as _step:
            completed_base_frame = pd.read_parquet(completed_extraction.base_path)
            _step.set_frame_after(completed_base_frame)
        with stage4_recorder.step(
            "target_engineer.engineer",
            frame_before=completed_base_frame,
        ) as _step:
            target_result = PromotionTargetEngineer().engineer(completed_base_frame)
            _step.set_frame_after(target_result.frame)
        feature_result = PromotionFeatureEngineer().engineer(
            target_result.frame,
            step_recorder=lambda name, before, after, elapsed: stage4_recorder.record(
                step_name=f"feature_pipeline.{name}",
                elapsed_seconds=elapsed,
                frame_before=before,
                frame_after=after,
            ),
        )
        with stage4_recorder.step(
            "dataset_assembler.assemble_training_dataset",
            frame_before=feature_result.frame,
        ) as _step:
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id=run_id,
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=settings.artifacts,
                negative_stock_policy=NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED,
            )
            _step.set_frame_after(dataset.frame)
        stage4_performance_summary_json_path = (
            settings.artifacts.stage4_performance_summary_json_path(run_id)
        )
        stage4_performance_summary_csv_path = (
            settings.artifacts.stage4_performance_summary_csv_path(run_id)
        )
        stage4_recorder.persist(
            json_path=stage4_performance_summary_json_path,
            csv_path=stage4_performance_summary_csv_path,
        )
        _stage4_negative_stock_quarantine_count = int(
            getattr(
                dataset.manifest.validation_report,
                "negative_stock_quarantined_rows",
                0,
            )
        )
        if _stage4_negative_stock_quarantine_count > 0:
            progress.detail(
                "stage4_negative_stock_quarantined_rows: "
                f"{_stage4_negative_stock_quarantine_count}"
            )
            progress.detail(
                "stage4_negative_stock_classification_counts: "
                f"{dataset.manifest.validation_report.negative_stock_quarantine_classification_counts}"
            )
        progress.complete_stage(
            row_count=dataset.manifest.row_count,
            file_count=2,
            output_paths=(
                dataset.dataset_path,
                dataset.manifest_path,
                str(stage4_performance_summary_json_path),
                str(stage4_performance_summary_csv_path),
            ),
            note="Training-ready dataset and manifest persisted.",
        )
        
        if _should_stop_after_stage(4):
            progress.detail("proof_mode_stage_stop: Stopping after Stage 4 as requested")
            return _build_partial_operational_cycle_artifacts(
                run_id=run_id,
                settings=settings,
                nas_bootstrap_artifacts=nas_bootstrap_artifacts,
                local_inspection_artifacts=local_inspection_artifacts,
                completed_extraction=completed_extraction,
                dataset=dataset,
                progress=progress,
                stop_after_stage=4,
            )

        progress.start_stage(5, OPERATIONAL_CYCLE_STAGE_COUNT, "Train model bundle")
        progress.detail("action: fit the reusable model bundle from the governed training dataset")
        with progress.heartbeat(
            "training reusable model family",
            heartbeat_seconds=8.0,
            row_count=int(len(dataset.frame.index)),
        ):
            training_artifacts = PromotionModelTrainer().train(
                run_id=run_id,
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=settings.artifacts,
                target_mode=resolved_target_mode,
            )
        progress.complete_stage(
            row_count=int(len(dataset.frame.index)),
            file_count=len(training_artifacts.artifact_files) + 4,
            output_paths=(training_artifacts.manifest_path, training_artifacts.metrics_path),
            note="Reusable model bundle, schema, and metrics persisted.",
        )

        progress.start_stage(6, OPERATIONAL_CYCLE_STAGE_COUNT, "Extract future promotions")
        progress.detail(f"action: {_stage_subtask_message('future', execution_mode)}")

        stage6_guardrail_path_obj = (
            settings.artifacts.manifests_run_root(resolved_score_run_id)
            / "stage6_future_extraction_guardrail.json"
        )
        stage6_plan_path_obj = (
            settings.artifacts.manifests_run_root(resolved_score_run_id)
            / "stage6_future_extraction_plan.json"
        )
        stage6_failure_summary_path_obj = (
            settings.artifacts.manifests_run_root(resolved_score_run_id)
            / "stage6_future_extraction_failure_summary.json"
        )
        stage6_guardrail_path_obj.parent.mkdir(parents=True, exist_ok=True)
        stage6_guardrail_path = str(stage6_guardrail_path_obj)
        stage6_plan_path = str(stage6_plan_path_obj)
        requested_execution_scope_hint = (
            "proof_bounded_scope" if proof_mode else "full_scope"
        )
        stage6_rerun_recommendation = (
            "python -m runtime.promotions.run_promotions_operator live "
            f"--run-id {run_id} "
            f"--as-of-date {settings.as_of_date.isoformat()} "
            "--proof-mode"
        )
        if proof_max_future_promotions is not None:
            stage6_rerun_recommendation += (
                f" --proof-max-future-promotions {proof_max_future_promotions}"
            )
        if proof_future_fallback_mode is not None:
            stage6_rerun_recommendation += (
                f" --proof-future-fallback-mode {proof_future_fallback_mode}"
            )
        if proof_future_fallback_topn_limit is not None:
            stage6_rerun_recommendation += (
                " --proof-future-fallback-topn-limit "
                f"{proof_future_fallback_topn_limit}"
            )
        if proof_future_fallback_slice_promotions is not None:
            stage6_rerun_recommendation += (
                " --proof-future-fallback-slice-promotions "
                f"{proof_future_fallback_slice_promotions}"
            )

        # Authoritative Stage 6 planner contract: derive scope and query options once.
        try:
            stage6_plan = _plan_stage6_future_extraction(
                proof_mode=proof_mode,
                proof_max_future_promotions=proof_max_future_promotions,
                proof_future_fallback_mode=proof_future_fallback_mode,
                proof_future_fallback_topn_limit=proof_future_fallback_topn_limit,
                proof_future_fallback_slice_promotions=(
                    proof_future_fallback_slice_promotions
                ),
                query_timeout_seconds=settings.sql.query_timeout_seconds,
            )
        except Exception as planner_error:
            planner_operator_message = (
                "Stage 6 planner rejected the requested proof contract before SQL render."
            )
            stage6_guardrail_payload: dict[str, object] = {
                "stage": 6,
                "run_id": run_id,
                "selection_mode": "future",
                "requested_proof_mode_flag": proof_mode,
                "requested_proof_max_future_promotions": proof_max_future_promotions,
                "requested_proof_future_fallback_mode": proof_future_fallback_mode,
                "requested_proof_future_fallback_topn_limit": (
                    proof_future_fallback_topn_limit
                ),
                "requested_proof_future_fallback_slice_promotions": (
                    proof_future_fallback_slice_promotions
                ),
                "requested_execution_scope_hint": requested_execution_scope_hint,
                "resolved_execution_scope": None,
                "execution_scope": None,
                "resolved_future_extraction_mode": None,
                "future_extraction_mode": None,
                "proof_mode": proof_mode,
                "proof_bounded": False,
                "proof_max_future_promotions": proof_max_future_promotions,
                "proof_fallback_used": False,
                "proof_fallback_mode": None,
                "proof_fallback_reason": None,
                "future_query_options": _serialize_stage6_query_options(None),
                "operator_message": planner_operator_message,
                "planner_verdict": "PLANNER_REJECTED",
                "proof_bounding_supported_flag": False,
                "proof_bounding_reason": str(planner_error),
                "query_timeout_seconds": settings.sql.query_timeout_seconds,
                "guardrail_reason": "planner rejected requested Stage 6 proof contract",
                "timeout_risk_remaining": True,
                "planned_at_utc": datetime.now(tz=UTC).isoformat(),
                "rerun_recommendation": stage6_rerun_recommendation,
            }
            stage6_plan_payload: dict[str, object] = {
                "stage": 6,
                "run_id": run_id,
                "selection_mode": "future",
                "requested_proof_mode_flag": proof_mode,
                "requested_proof_max_future_promotions": proof_max_future_promotions,
                "requested_proof_future_fallback_mode": proof_future_fallback_mode,
                "requested_proof_future_fallback_topn_limit": (
                    proof_future_fallback_topn_limit
                ),
                "requested_proof_future_fallback_slice_promotions": (
                    proof_future_fallback_slice_promotions
                ),
                "requested_execution_scope_hint": requested_execution_scope_hint,
                "resolved_execution_scope": None,
                "execution_scope": None,
                "resolved_future_extraction_mode": None,
                "future_extraction_mode": None,
                "proof_mode": proof_mode,
                "proof_bounded": False,
                "proof_max_future_promotions": proof_max_future_promotions,
                "proof_fallback_used": False,
                "proof_fallback_mode": None,
                "proof_fallback_reason": None,
                "future_query_options": _serialize_stage6_query_options(None),
                "operator_message": planner_operator_message,
                "planner_verdict": "PLANNER_REJECTED",
                "proof_bounding_supported_flag": False,
                "proof_bounding_reason": str(planner_error),
                "guardrail_reason": "planner rejected requested Stage 6 proof contract",
                "query_timeout_seconds": settings.sql.query_timeout_seconds,
                "timeout_risk_remaining": True,
                "created_at_utc": datetime.now(tz=UTC).isoformat(),
                "rerun_recommendation": stage6_rerun_recommendation,
            }
            stage6_failure_summary_payload = {
                "stage": 6,
                "failure_phase": "planner_rejection",
                "run_id": run_id,
                "score_run_id": resolved_score_run_id,
                "selection_mode": "future",
                "requested_proof_mode_flag": proof_mode,
                "requested_proof_max_future_promotions": proof_max_future_promotions,
                "requested_proof_future_fallback_mode": proof_future_fallback_mode,
                "requested_proof_future_fallback_topn_limit": (
                    proof_future_fallback_topn_limit
                ),
                "requested_proof_future_fallback_slice_promotions": (
                    proof_future_fallback_slice_promotions
                ),
                "requested_execution_scope_hint": requested_execution_scope_hint,
                "resolved_execution_scope": None,
                "execution_scope": None,
                "resolved_future_extraction_mode": None,
                "future_extraction_mode": None,
                "proof_mode": proof_mode,
                "proof_bounded": False,
                "proof_max_future_promotions": proof_max_future_promotions,
                "proof_fallback_used": False,
                "proof_fallback_mode": None,
                "proof_fallback_reason": None,
                "future_query_options": _serialize_stage6_query_options(None),
                "planner_verdict": "PLANNER_REJECTED",
                "operator_message": planner_operator_message,
                "proof_bounding_supported_flag": False,
                "proof_bounding_reason": str(planner_error),
                "guardrail_reason": "planner rejected requested Stage 6 proof contract",
                "query_timeout_seconds": settings.sql.query_timeout_seconds,
                "failure_recorded_at_utc": datetime.now(tz=UTC).isoformat(),
                "exception_type": type(planner_error).__name__,
                "reason": str(planner_error),
                "guardrail_path": stage6_guardrail_path,
                "plan_path": stage6_plan_path,
                "rerun_recommendation": stage6_rerun_recommendation,
            }
            stage6_guardrail_path_obj.write_text(
                json.dumps(stage6_guardrail_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            stage6_plan_path_obj.write_text(
                json.dumps(stage6_plan_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            stage6_failure_summary_path_obj.write_text(
                json.dumps(stage6_failure_summary_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            stage6_failure_summary_path = str(stage6_failure_summary_path_obj)
            setattr(planner_error, "selection_mode", "future")
            setattr(planner_error, "stage6_future_extraction_guardrail_path", stage6_guardrail_path)
            setattr(planner_error, "stage6_future_extraction_plan_path", stage6_plan_path)
            setattr(
                planner_error,
                "stage6_future_extraction_failure_summary_path",
                stage6_failure_summary_path,
            )
            setattr(planner_error, "stage6_execution_scope", "not_planned")
            setattr(planner_error, "stage6_planner_verdict", "PLANNER_REJECTED")
            setattr(planner_error, "stage6_operator_message", planner_operator_message)
            setattr(planner_error, "stage6_future_extraction_mode", "not_planned")
            setattr(planner_error, "stage6_proof_fallback_used", False)
            setattr(planner_error, "stage6_proof_fallback_mode", None)
            setattr(planner_error, "stage6_proof_fallback_reason", None)
            raise

        stage6_guardrail_payload: dict[str, object] = {
            "stage": 6,
            "run_id": run_id,
            "selection_mode": "future",
            "requested_proof_mode_flag": proof_mode,
            "requested_proof_max_future_promotions": proof_max_future_promotions,
            "requested_proof_future_fallback_mode": proof_future_fallback_mode,
            "requested_proof_future_fallback_topn_limit": proof_future_fallback_topn_limit,
            "requested_proof_future_fallback_slice_promotions": (
                proof_future_fallback_slice_promotions
            ),
            "requested_execution_scope_hint": requested_execution_scope_hint,
            "resolved_execution_scope": stage6_plan.execution_scope,
            "execution_scope": stage6_plan.execution_scope,
            "resolved_future_extraction_mode": stage6_plan.future_extraction_mode,
            "future_extraction_mode": stage6_plan.future_extraction_mode,
            "proof_mode": proof_mode,
            "proof_bounded": stage6_plan.proof_bounded,
            "proof_max_future_promotions": stage6_plan.proof_max_future_promotions,
            "proof_fallback_used": stage6_plan.proof_fallback_used,
            "proof_fallback_mode": stage6_plan.proof_fallback_mode,
            "proof_fallback_reason": stage6_plan.proof_fallback_reason,
            "future_query_options": _serialize_stage6_query_options(
                stage6_plan.future_query_options
            ),
            "operator_message": stage6_plan.operator_message,
            "planner_verdict": stage6_plan.planner_verdict,
            "proof_bounding_supported_flag": stage6_plan.proof_bounding_supported_flag,
            "proof_bounding_reason": stage6_plan.proof_bounding_reason,
            "query_timeout_seconds": stage6_plan.query_timeout_seconds,
            "guardrail_reason": stage6_plan.guardrail_reason,
            "timeout_risk_remaining": not stage6_plan.proof_bounded,
            "planned_at_utc": datetime.now(tz=UTC).isoformat(),
            "rerun_recommendation": stage6_rerun_recommendation,
        }
        stage6_plan_payload: dict[str, object] = {
            "stage": 6,
            "run_id": run_id,
            "selection_mode": "future",
            "requested_proof_mode_flag": proof_mode,
            "requested_proof_max_future_promotions": proof_max_future_promotions,
            "requested_proof_future_fallback_mode": proof_future_fallback_mode,
            "requested_proof_future_fallback_topn_limit": proof_future_fallback_topn_limit,
            "requested_proof_future_fallback_slice_promotions": (
                proof_future_fallback_slice_promotions
            ),
            "requested_execution_scope_hint": requested_execution_scope_hint,
            "resolved_execution_scope": stage6_plan.execution_scope,
            "execution_scope": stage6_plan.execution_scope,
            "resolved_future_extraction_mode": stage6_plan.future_extraction_mode,
            "future_extraction_mode": stage6_plan.future_extraction_mode,
            "proof_mode": proof_mode,
            "proof_bounded": stage6_plan.proof_bounded,
            "proof_max_future_promotions": stage6_plan.proof_max_future_promotions,
            "proof_fallback_used": stage6_plan.proof_fallback_used,
            "proof_fallback_mode": stage6_plan.proof_fallback_mode,
            "proof_fallback_reason": stage6_plan.proof_fallback_reason,
            "future_query_options": _serialize_stage6_query_options(
                stage6_plan.future_query_options
            ),
            "operator_message": stage6_plan.operator_message,
            "planner_verdict": stage6_plan.planner_verdict,
            "proof_bounding_supported_flag": stage6_plan.proof_bounding_supported_flag,
            "proof_bounding_reason": stage6_plan.proof_bounding_reason,
            "guardrail_reason": stage6_plan.guardrail_reason,
            "query_timeout_seconds": stage6_plan.query_timeout_seconds,
            "timeout_risk_remaining": not stage6_plan.proof_bounded,
            "created_at_utc": datetime.now(tz=UTC).isoformat(),
            "rerun_recommendation": stage6_rerun_recommendation,
        }
        stage6_guardrail_path_obj.write_text(
            json.dumps(stage6_guardrail_payload, indent=2), encoding="utf-8"
        )
        stage6_plan_path_obj.write_text(
            json.dumps(stage6_plan_payload, indent=2), encoding="utf-8"
        )
        progress.detail(
            f"stage6_requested_proof_mode_flag: {str(proof_mode).lower()}"
        )
        progress.detail(
            "stage6_requested_proof_max_future_promotions: "
            f"{proof_max_future_promotions if proof_max_future_promotions is not None else 'none'}"
        )
        progress.detail(f"stage6_execution_scope: {stage6_plan.execution_scope}")
        progress.detail(
            f"stage6_future_extraction_mode: {stage6_plan.future_extraction_mode}"
        )
        progress.detail(f"stage6_planner_verdict: {stage6_plan.planner_verdict}")
        progress.detail(f"stage6_operator_message: {stage6_plan.operator_message}")
        if stage6_plan.proof_max_future_promotions is not None:
            progress.detail(
                "stage6_proof_max_future_promotions: "
                f"{stage6_plan.proof_max_future_promotions}"
            )
        progress.detail(
            "stage6_proof_fallback_used: "
            f"{str(stage6_plan.proof_fallback_used).lower()}"
        )
        if stage6_plan.proof_fallback_mode is not None:
            progress.detail(
                f"stage6_proof_fallback_mode: {stage6_plan.proof_fallback_mode}"
            )
        if stage6_plan.proof_fallback_reason is not None:
            progress.detail(
                f"stage6_proof_fallback_reason: {stage6_plan.proof_fallback_reason}"
            )
        if stage6_plan.future_query_options is not None:
            progress.detail(
                "stage6_query_options: "
                f"extraction_mode={stage6_plan.future_query_options.extraction_mode}, "
                f"limit_promotions={stage6_plan.future_query_options.limit_promotions}"
            )
        if not stage6_plan.proof_bounded:
            progress.detail(
                "stage6_timeout_risk: full-scope future extraction remains subject to live SQL timeout pressure"
            )
        progress.detail(f"stage6_guardrail_path: {stage6_guardrail_path}")
        progress.detail(f"stage6_plan_path: {stage6_plan_path}")

        try:
            with progress.heartbeat(
                _stage_subtask_message("future", execution_mode),
                heartbeat_seconds=8.0,
            ):
                future_extraction = extraction_runner(
                    settings=settings,
                    run_id=resolved_score_run_id,
                    selection_mode="future",
                    query_options=stage6_plan.future_query_options,
                    progress_callback=lambda subtask: progress.update_heartbeat(
                        subtask=subtask,
                        emit_now=True,
                    ),
                )
        except Exception as error:
            stage6_failure_summary_path_obj.parent.mkdir(parents=True, exist_ok=True)
            stage6_failure_summary_payload = {
                "stage": 6,
                "failure_phase": "sql_runtime_failure",
                "run_id": run_id,
                "score_run_id": resolved_score_run_id,
                "selection_mode": "future",
                "requested_proof_mode_flag": proof_mode,
                "requested_proof_max_future_promotions": proof_max_future_promotions,
                "requested_proof_future_fallback_mode": proof_future_fallback_mode,
                "requested_proof_future_fallback_topn_limit": (
                    proof_future_fallback_topn_limit
                ),
                "requested_proof_future_fallback_slice_promotions": (
                    proof_future_fallback_slice_promotions
                ),
                "requested_execution_scope_hint": requested_execution_scope_hint,
                "resolved_execution_scope": stage6_plan.execution_scope,
                "execution_scope": stage6_plan.execution_scope,
                "resolved_future_extraction_mode": stage6_plan.future_extraction_mode,
                "future_extraction_mode": stage6_plan.future_extraction_mode,
                "proof_mode": proof_mode,
                "proof_bounded": stage6_plan.proof_bounded,
                "proof_max_future_promotions": stage6_plan.proof_max_future_promotions,
                "proof_fallback_used": stage6_plan.proof_fallback_used,
                "proof_fallback_mode": stage6_plan.proof_fallback_mode,
                "proof_fallback_reason": stage6_plan.proof_fallback_reason,
                "future_query_options": _serialize_stage6_query_options(
                    stage6_plan.future_query_options
                ),
                "planner_verdict": stage6_plan.planner_verdict,
                "operator_message": stage6_plan.operator_message,
                "proof_bounding_supported_flag": stage6_plan.proof_bounding_supported_flag,
                "proof_bounding_reason": stage6_plan.proof_bounding_reason,
                "guardrail_reason": stage6_plan.guardrail_reason,
                "query_timeout_seconds": stage6_plan.query_timeout_seconds,
                "failure_recorded_at_utc": datetime.now(tz=UTC).isoformat(),
                "exception_type": type(error).__name__,
                "reason": str(error),
                "current_sql_subphase": getattr(error, "current_sql_subphase", None),
                "rendered_sql_path": getattr(error, "rendered_sql_path", None),
                "rendered_sql_parameters_path": getattr(
                    error,
                    "rendered_sql_parameters_path",
                    None,
                ),
                "extraction_telemetry_json_path": getattr(
                    error,
                    "extraction_telemetry_json_path",
                    None,
                ),
                "extraction_telemetry_csv_path": getattr(
                    error,
                    "extraction_telemetry_csv_path",
                    None,
                ),
                "sql_diagnostics_summary_json_path": getattr(
                    error,
                    "sql_diagnostics_summary_json_path",
                    None,
                ),
                "sql_diagnostics_summary_txt_path": getattr(
                    error,
                    "sql_diagnostics_summary_txt_path",
                    None,
                ),
                "guardrail_path": stage6_guardrail_path,
                "plan_path": stage6_plan_path,
                "rerun_recommendation": stage6_rerun_recommendation,
            }
            stage6_failure_summary_path_obj.write_text(
                json.dumps(stage6_failure_summary_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            stage6_failure_summary_path = str(stage6_failure_summary_path_obj)
            setattr(error, "stage6_future_extraction_guardrail_path", stage6_guardrail_path)
            setattr(error, "stage6_future_extraction_plan_path", stage6_plan_path)
            setattr(
                error,
                "stage6_future_extraction_failure_summary_path",
                stage6_failure_summary_path,
            )
            setattr(error, "stage6_execution_scope", stage6_plan.execution_scope)
            setattr(error, "stage6_planner_verdict", stage6_plan.planner_verdict)
            setattr(error, "stage6_operator_message", stage6_plan.operator_message)
            setattr(error, "stage6_future_extraction_mode", stage6_plan.future_extraction_mode)
            setattr(error, "stage6_proof_fallback_used", stage6_plan.proof_fallback_used)
            setattr(error, "stage6_proof_fallback_mode", stage6_plan.proof_fallback_mode)
            setattr(error, "stage6_proof_fallback_reason", stage6_plan.proof_fallback_reason)
            raise

        progress.complete_stage(
            row_count=int(future_extraction.manifest.get("row_count", 0) or 0),
            file_count=10,
            output_paths=(
                future_extraction.base_path,
                future_extraction.manifest_path,
                stage6_guardrail_path,
                stage6_plan_path,
                *( 
                    (future_extraction.rendered_sql_path,)
                    if future_extraction.rendered_sql_path is not None
                    else ()
                ),
                future_extraction.telemetry_json_path,
                future_extraction.diagnostics_summary_json_path,
            ),
            note="Future promotions base extract persisted.",
        )

        progress.start_stage(7, OPERATIONAL_CYCLE_STAGE_COUNT, "Score future promotions")
        progress.detail("action: engineer inference features, score future rows, and write technical prediction reports")
        with progress.heartbeat(
            "loading historical reference rows",
            heartbeat_seconds=8.0,
            row_count=int(len(future_extraction.frame.index)),
        ):
            historical_reference_frame = pd.read_parquet(dataset.dataset_path)
            progress.update_heartbeat(
                subtask="scoring future promotions against the reusable model bundle",
                row_count=int(len(future_extraction.frame.index)),
            )
            scoring_artifacts = PromotionModelScorer().score(
                run_id=resolved_score_run_id,
                model_run_id=run_id,
                future_base_frame=future_extraction.frame,
                historical_reference_frame=historical_reference_frame,
                artifact_paths=settings.artifacts,
            )
            progress.update_heartbeat(
                subtask="writing technical prediction reports",
                row_count=int(len(scoring_artifacts.row_frame.index)),
            )
            reporting_artifacts = PromotionReportBuilder().write_reports(
                run_id=resolved_score_run_id,
                scored_rows=scoring_artifacts.row_frame,
                artifact_paths=settings.artifacts,
            )
        progress.complete_stage(
            row_count=int(len(scoring_artifacts.row_frame.index)),
            file_count=1 + len(scoring_artifacts.summary_paths) + len(reporting_artifacts.report_paths),
            output_paths=(
                scoring_artifacts.row_predictions_path,
                scoring_artifacts.manifest_path,
                reporting_artifacts.report_paths["report_manifest"],
            ),
            note="Row predictions, summaries, and technical score reports persisted.",
        )

        if scoring_artifacts.row_frame.empty:
            return _complete_zero_future_scored_rows_noop(
                settings=settings,
                run_id=run_id,
                score_run_id=resolved_score_run_id,
                decision_surface_run_id=resolved_decision_surface_run_id,
                execution_mode=execution_mode,
                target_mode=target_mode,
                resolved_target_mode=resolved_target_mode,
                manifest_path=manifest_path,
                nas_bootstrap_artifacts=nas_bootstrap_artifacts,
                completed_extraction=completed_extraction,
                future_extraction=future_extraction,
                dataset=dataset,
                training_artifacts=training_artifacts,
                scoring_artifacts=scoring_artifacts,
                reporting_artifacts=reporting_artifacts,
                progress=progress,
                requested_completed_partitioning=requested_completed_partitioning,
                effective_completed_partitioning=effective_completed_partitioning,
                completed_partition_retry_records=completed_partition_retry_records,
                completed_partition_retries_json_path=completed_partition_retries_json_path,
                completed_partition_retries_csv_path=completed_partition_retries_csv_path,
                stage6_plan=stage6_plan,
                stage6_guardrail_path=stage6_guardrail_path,
                stage6_plan_path=stage6_plan_path,
            )

        decision_surface_artifacts = run_decision_surface_for_scored_rows(
            future_scored_frame=scoring_artifacts.row_frame,
            historical_dataset_path=dataset.dataset_path,
            historical_dataset_run_id=run_id,
            model_bundle_path=str(settings.artifacts.model_family_root(run_id)),
            model_run_id=run_id,
            artifact_root=str(settings.artifacts.root),
            run_id=resolved_decision_surface_run_id,
            as_of_date=settings.as_of_date.isoformat(),
            minimum_cohort_sample_size=minimum_cohort_sample_size,
            similarity_threshold=similarity_threshold,
            archetype_confidence_floor=archetype_confidence_floor,
            row_model_confidence_floor=row_model_confidence_floor,
            operator_progress=progress,
            decision_surface_stage_number=8,
            inspection_stage_number=9,
            total_stages=OPERATIONAL_CYCLE_STAGE_COUNT,
        )

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_payload = PromotionOperationalCycleManifest(
            run_id=run_id,
            score_run_id=resolved_score_run_id,
            decision_surface_run_id=resolved_decision_surface_run_id,
            executed_at_utc=datetime.now(tz=UTC).isoformat(),
            as_of_date=settings.as_of_date.isoformat(),
            artifact_root=str(settings.artifacts.root),
            nas_root=str(settings.artifacts.root),
            local_inspection_root=(
                str(settings.artifacts.local_inspection_root)
                if settings.artifacts.local_inspection_root is not None
                else None
            ),
            execution_mode=execution_mode,
            runtime_settings={
                "server": settings.sql.server,
                "database": settings.sql.database,
                "schema": settings.sql.schema,
                "promotion_advice_table": settings.sql.promotion_advice_table,
                "pwlogd_table": settings.sql.pwlogd_table,
                "odbc_driver": settings.sql.odbc_driver,
                "connect_timeout_seconds": settings.sql.connect_timeout_seconds,
                "connect_retry_attempts": settings.sql.connect_retry_attempts,
                "connect_retry_backoff_seconds": settings.sql.connect_retry_backoff_seconds,
                "query_timeout_seconds": settings.sql.query_timeout_seconds,
                "encrypt": settings.sql.encrypt,
                "trust_server_certificate": settings.sql.trust_server_certificate,
                "requested_target_mode": target_mode,
                "resolved_target_mode": resolved_target_mode,
                "requested_completed_partitioning": (
                    requested_completed_partitioning.to_dict()
                    if requested_completed_partitioning is not None
                    else None
                ),
                "completed_partitioning": (
                    effective_completed_partitioning.to_dict()
                    if effective_completed_partitioning is not None
                    else None
                ),
                "completed_extraction_runtime": settings.completed_extraction_runtime.to_dict(),
                "completed_preflight_planner": settings.completed_preflight_planner.to_dict(),
            },
            nas_bootstrap=nas_bootstrap_artifacts.to_dict() if nas_bootstrap_artifacts else None,
            completed_extraction={
                "run_id": run_id,
                "selection_mode": completed_extraction.selection_mode,
                "extraction_mode": completed_extraction.extraction_mode,
                "fetch_mode": completed_extraction.fetch_mode,
                "chunk_mode": completed_extraction.chunk_mode,
                "chunk_count": completed_extraction.chunk_count,
                "completed_chunk_count": completed_extraction.completed_chunk_count,
                "cumulative_rows_written": completed_extraction.cumulative_rows_written,
                "batch_count": completed_extraction.batch_count,
                "finalized_batch_count": completed_extraction.finalized_batch_count,
                "resumed_batch_count": completed_extraction.resumed_batch_count,
                "rebuilt_batch_count": completed_extraction.rebuilt_batch_count,
                "total_landed_rows": completed_extraction.total_landed_rows,
                "completion_state": completed_extraction.completion_state,
                "partition_completion_state": completed_extraction.partition_completion_state,
                "resume_state": completed_extraction.resume_state,
                "skipped_due_to_existing_completion": (
                    completed_extraction.skipped_due_to_existing_completion
                ),
                "partition_strategy": completed_extraction.partition_strategy,
                "partition_count": completed_extraction.partition_count,
                "partition_index": completed_extraction.partition_index,
                "partition_progress_path": completed_extraction.partition_progress_path,
                "partition_completion_marker_path": (
                    completed_extraction.partition_completion_marker_path
                ),
                "preflight_summary_json_path": completed_extraction.preflight_summary_json_path,
                "preflight_summary_csv_path": completed_extraction.preflight_summary_csv_path,
                "rendered_preflight_sql_path": completed_extraction.rendered_preflight_sql_path,
                "rendered_preflight_sql_parameters_path": completed_extraction.rendered_preflight_sql_parameters_path,
                "preflight_verdict": completed_extraction.preflight_verdict,
                "preflight_reason": completed_extraction.preflight_reason,
                "estimated_cost_score": completed_extraction.estimated_cost_score,
                "estimated_extract_query_seconds": completed_extraction.estimated_extract_query_seconds,
                "fixed_overhead_seconds": completed_extraction.fixed_overhead_seconds,
                "variable_cost_signal": completed_extraction.variable_cost_signal,
                "cost_model_version": completed_extraction.cost_model_version,
                "cost_guardrail_verdict": completed_extraction.cost_guardrail_verdict,
                "cost_guardrail_reason": completed_extraction.cost_guardrail_reason,
                "recommended_partition_strategy": completed_extraction.recommended_partition_strategy,
                "recommended_partition_count": completed_extraction.recommended_partition_count,
                "completed_preflight_cost_diagnostic_path": completed_extraction.completed_preflight_cost_diagnostic_path,
                "completed_preflight_model_learning_diagnostic_path": completed_extraction.completed_preflight_model_learning_diagnostic_path,
                "completed_proof_fallback_used": completed_extraction.completed_proof_fallback_used,
                "completed_proof_fallback_mode": completed_extraction.completed_proof_fallback_mode,
                "completed_proof_fallback_reason": completed_extraction.completed_proof_fallback_reason,
                "base_path": completed_extraction.base_path,
                "manifest_path": completed_extraction.manifest_path,
                "partition_summary_path": completed_extraction.partition_summary_path,
                "rendered_sql_path": completed_extraction.rendered_sql_path,
                "rendered_sql_parameters_path": completed_extraction.rendered_sql_parameters_path,
                "telemetry_json_path": completed_extraction.telemetry_json_path,
                "telemetry_csv_path": completed_extraction.telemetry_csv_path,
                "sql_diagnostics_summary_json_path": completed_extraction.diagnostics_summary_json_path,
                "sql_diagnostics_summary_txt_path": completed_extraction.diagnostics_summary_txt_path,
                "candidate_promotion_row_count": completed_extraction.candidate_promotion_row_count,
                "manifest": completed_extraction.manifest,
                "partition_retries_json_path": completed_partition_retries_json_path,
                "partition_retries_csv_path": completed_partition_retries_csv_path,
                "repartition_attempt_count": len(completed_partition_retry_records),
            },
            training_dataset={
                "run_id": run_id,
                "dataset_path": dataset.dataset_path,
                "manifest_path": dataset.manifest_path,
                "manifest": dataset.manifest.to_dict(),
            },
            model_bundle={
                "run_id": run_id,
                "artifact_root": training_artifacts.artifact_root,
                "manifest_path": training_artifacts.manifest_path,
                "metrics_path": training_artifacts.metrics_path,
                "inference_schema_path": training_artifacts.inference_schema_path,
                "feature_list_path": training_artifacts.feature_list_path,
                "target_mode": training_artifacts.target_mode,
                "artifact_files": training_artifacts.artifact_files,
            },
            future_extraction={
                "run_id": resolved_score_run_id,
                "selection_mode": future_extraction.selection_mode,
                "extraction_mode": future_extraction.extraction_mode,
                "partition_strategy": future_extraction.partition_strategy,
                "partition_count": future_extraction.partition_count,
                "partition_index": future_extraction.partition_index,
                "base_path": future_extraction.base_path,
                "manifest_path": future_extraction.manifest_path,
                "partition_summary_path": future_extraction.partition_summary_path,
                "rendered_sql_path": future_extraction.rendered_sql_path,
                "rendered_sql_parameters_path": future_extraction.rendered_sql_parameters_path,
                "telemetry_json_path": future_extraction.telemetry_json_path,
                "telemetry_csv_path": future_extraction.telemetry_csv_path,
                "sql_diagnostics_summary_json_path": future_extraction.diagnostics_summary_json_path,
                "sql_diagnostics_summary_txt_path": future_extraction.diagnostics_summary_txt_path,
                "candidate_promotion_row_count": future_extraction.candidate_promotion_row_count,
                "manifest": future_extraction.manifest,
                "stage6_execution_scope": stage6_plan.execution_scope,
                "stage6_planner_verdict": stage6_plan.planner_verdict,
                "stage6_operator_message": stage6_plan.operator_message,
                "stage6_guardrail_reason": stage6_plan.guardrail_reason,
                "stage6_future_extraction_mode": stage6_plan.future_extraction_mode,
                "stage6_proof_max_future_promotions": stage6_plan.proof_max_future_promotions,
                "stage6_proof_fallback_used": stage6_plan.proof_fallback_used,
                "stage6_proof_fallback_mode": stage6_plan.proof_fallback_mode,
                "stage6_proof_fallback_reason": stage6_plan.proof_fallback_reason,
                "stage6_proof_bounding_supported_flag": stage6_plan.proof_bounding_supported_flag,
                "stage6_proof_bounding_reason": stage6_plan.proof_bounding_reason,
                "stage6_future_query_options": _serialize_stage6_query_options(
                    stage6_plan.future_query_options
                ),
                "stage6_future_extraction_guardrail_path": stage6_guardrail_path,
                "stage6_future_extraction_plan_path": stage6_plan_path,
            },
            scoring={
                "run_id": resolved_score_run_id,
                "manifest_path": scoring_artifacts.manifest_path,
                "row_predictions_path": scoring_artifacts.row_predictions_path,
                "summary_paths": scoring_artifacts.summary_paths,
                "report_paths": reporting_artifacts.report_paths,
            },
            decision_surface={
                "run_id": resolved_decision_surface_run_id,
                "manifest_path": decision_surface_artifacts.decision_surface_manifest_path,
                "metrics_path": decision_surface_artifacts.decision_surface_metrics_path,
                "diagnostics_summary_path": decision_surface_artifacts.diagnostics_summary_path,
                "calibration_summary_path": decision_surface_artifacts.calibration_summary_path,
                "calibration_thresholds_path": decision_surface_artifacts.calibration_thresholds_path,
                "execution_summary_path": decision_surface_artifacts.execution_summary_path,
                "inspection_manifest_path": decision_surface_artifacts.inspection_manifest_path,
                "report_paths": decision_surface_artifacts.report_paths,
                "inspection_report_paths": decision_surface_artifacts.inspection_report_paths,
                "cohort_report_manifest_path": decision_surface_artifacts.cohort_report_manifest_path,
            },
        ).to_dict()
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")

        # Stage 9.5 — Completed-promotion demand backtest. Uses the trainer's
        # honest out-of-sample test-set predictions (model never trained on
        # these rows) to produce row-level forecast-vs-actual artifacts plus
        # commercial segment splits, watchlist, and brief. Skip-classes are
        # honoured (e.g. no test-set rows or no observable actuals); contract
        # breaks fail loud. Insertion sits between Stage 9 and Stage 10 so
        # the audit step (which reads the cycle manifest) can record the
        # backtest section.
        progress.detail("action: write completed-promotion demand backtest artifacts")
        backtest_output_root = (
            settings.artifacts.operational_cycle_run_root(run_id)
            / "completed_promotions_demand_backtest"
        )
        try:
            backtest_paths = write_completed_promotion_demand_backtest(
                test_set_predictions_path=training_artifacts.test_set_predictions_path,
                output_root=backtest_output_root,
                run_id=run_id,
                as_of_date=settings.as_of_date.isoformat(),
            )
        except PromotionBacktestOrchestratorError:
            # Fail-loud: a contract break or duplicate-grain situation must
            # surface immediately and abort the cycle.
            raise
        manifest_payload["completed_promotions_demand_backtest"] = {
            "rows_csv_path": backtest_paths.rows_csv_path,
            "rows_parquet_path": backtest_paths.rows_parquet_path,
            "summary_json_path": backtest_paths.summary_json_path,
            "by_segment_csv_path": backtest_paths.by_segment_csv_path,
            "watchlist_csv_path": backtest_paths.watchlist_csv_path,
            "brief_md_path": backtest_paths.brief_md_path,
            "manifest_json_path": backtest_paths.manifest_json_path,
            "calibration_summary_json_path": backtest_paths.calibration_summary_json_path,
            "calibration_brief_md_path": backtest_paths.calibration_brief_md_path,
            "row_count_evaluated": backtest_paths.row_count_evaluated,
            "within_10pct_rate": backtest_paths.within_10pct_rate,
            "within_20pct_rate": backtest_paths.within_20pct_rate,
            "skip_reason": backtest_paths.skip_reason,
            "skip_class": backtest_paths.skip_class,
            "comparison_grain": "promotion_row_key",
        }
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8"
        )

        progress.start_stage(10, OPERATIONAL_CYCLE_STAGE_COUNT, "Build audit outputs")
        progress.detail("action: write audit summary tables, review tables, and the audit manifest")
        with progress.heartbeat(
            "writing operational audit outputs",
            heartbeat_seconds=8.0,
            row_count=int(len(scoring_artifacts.row_frame.index)),
        ):
            audit_artifacts = audit_operational_cycle(
                operational_cycle_manifest_path=str(manifest_path),
                artifact_root=str(settings.artifacts.root),
            )
        progress.complete_stage(
            file_count=sum(len(paths) for paths in audit_artifacts.report_paths.values()) + 3,
            output_paths=(
                audit_artifacts.audit_manifest_path,
                audit_artifacts.summary_json_path,
                audit_artifacts.summary_csv_path,
            ),
            note="Operational audit summary and review tables persisted.",
        )

        progress.start_stage(11, OPERATIONAL_CYCLE_STAGE_COUNT, "Build store download outputs")
        progress.detail("action: write master, per-store, and per-store-per-promotion store-facing CSV packs")
        with progress.heartbeat(
            "writing the store-facing CSV execution pack",
            heartbeat_seconds=8.0,
            row_count=int(len(scoring_artifacts.row_frame.index)),
            file_count=4,
        ):
            decision_surface_frame = pd.read_parquet(
                decision_surface_artifacts.report_paths["promotion_decision_surface"]["parquet"]
            )
            store_prediction_artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id=run_id,
                as_of_date=settings.as_of_date.isoformat(),
                decision_surface_frame=decision_surface_frame,
                artifact_paths=settings.artifacts,
                completed_backtest_summary_path=backtest_paths.summary_json_path,
            )
        progress.complete_stage(
            row_count=store_prediction_artifacts.row_count,
            file_count=store_prediction_artifacts.generated_file_count,
            output_paths=_unique_output_paths(
                store_prediction_artifacts.master_csv_path,
                store_prediction_artifacts.csv_path,
                store_prediction_artifacts.manifest_csv_path,
                store_prediction_artifacts.manifest_path,
            ),
            note="Store-facing master/per-store/per-store-promotion CSV execution pack and manifests persisted.",
        )

        progress.start_stage(12, OPERATIONAL_CYCLE_STAGE_COUNT, "Publish client/store execution packs")
        progress.detail("action: publish POS-ready and review-ready files to retailer/store prediction folders")
        with progress.heartbeat(
            "publishing client/store execution packs",
            heartbeat_seconds=8.0,
            row_count=int(store_prediction_artifacts.row_count),
        ):
            store_download_frame = pd.read_csv(store_prediction_artifacts.master_csv_path)
            commercial_publish_artifacts = StorePredictionPublisher().publish(
                run_id=run_id,
                as_of_date=settings.as_of_date.isoformat(),
                scored_decision_surface_frame=decision_surface_frame,
                store_download_frame=store_download_frame,
                artifact_paths=settings.artifacts,
                model_version=run_id,
                planning_horizon_days=35,
                allow_reprediction=False,
                strict_store_mapping=(
                    execution_mode == "live_sql"
                    and settings.artifacts.promotion_store_client_mapping_path().exists()
                ),
            )
        progress.detail(
            f"stores_published: {commercial_publish_artifacts.stores_published}"
        )
        progress.detail(
            f"promotion_predictions_published: {commercial_publish_artifacts.promotion_cycles_published}"
        )
        progress.detail(
            f"pos_upload_rows_written: {commercial_publish_artifacts.pos_upload_row_count}"
        )
        progress.detail(
            f"pos_excluded_rows: {commercial_publish_artifacts.pos_excluded_row_count}"
        )
        progress.detail(
            f"publish_status: {commercial_publish_artifacts.publish_status}"
        )
        progress.detail(
            f"publish_status_reason: {commercial_publish_artifacts.publish_status_reason}"
        )
        if commercial_publish_artifacts.publish_status == "NOOP_ALREADY_PUBLISHED":
            progress.detail(
                "stage12_noop_message: Stage 12 completed with NOOP_ALREADY_PUBLISHED: "
                f"{commercial_publish_artifacts.skipped_due_to_registry_duplicate_count} rows skipped by registry duplicate policy; "
                "no new client files written."
            )
        progress.detail(
            "skipped_duplicate_predictions: "
            f"{commercial_publish_artifacts.skipped_duplicate_prediction_count}"
        )
        # Governed Stage 11/12 publishability transparency split.
        commercial_publishability_split = build_commercial_publishability_split(
            store_download_frame=store_download_frame,
            pos_upload_row_count=int(commercial_publish_artifacts.pos_upload_row_count),
            pos_excluded_row_count=int(commercial_publish_artifacts.pos_excluded_row_count),
            stage12_review_only_row_count=int(
                commercial_publish_artifacts.skipped_due_to_review_count
            ),
            registry_duplicate_row_count=int(
                commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
            ),
        )
        progress.detail(
            "publishability_split: "
            f"true_zero={commercial_publishability_split.true_zero_demand_rows} "
            f"evidence_zero={commercial_publishability_split.evidence_supported_zero_rows} "
            f"artificial_collapse={commercial_publishability_split.artificial_collapse_rows} "
            f"registry_duplicate={commercial_publishability_split.registry_duplicate_rows} "
            f"review={commercial_publishability_split.review_required_rows} "
            f"policy_excluded={commercial_publishability_split.policy_excluded_legitimate_rows} "
            f"published={commercial_publishability_split.final_publishable_rows}"
        )
        progress.detail(
            f"publishability_headline: {commercial_publishability_split.headline_class} — "
            f"{commercial_publishability_split.headline_message}"
        )
        commercial_publishability_split_path = (
            settings.artifacts.inspection_run_root(run_id)
            / "commercial_publishability_split.json"
        )
        commercial_publishability_split_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_publishability_split_path.write_text(
            json.dumps(commercial_publishability_split.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        progress.complete_stage(
            row_count=commercial_publish_artifacts.pos_upload_row_count,
            file_count=(
                len(commercial_publish_artifacts.pos_upload_paths)
                + len(commercial_publish_artifacts.review_paths)
                + len(commercial_publish_artifacts.summary_paths)
                + len(commercial_publish_artifacts.store_cycle_manifest_paths)
                + len(commercial_publish_artifacts.diagnostics_paths)
                + len(commercial_publish_artifacts.skipped_paths)
            ),
            output_paths=(
                commercial_publish_artifacts.prediction_registry_path,
                *(commercial_publish_artifacts.store_cycle_manifest_paths[:1]),
                *(commercial_publish_artifacts.pos_upload_paths[:1]),
                *(commercial_publish_artifacts.review_paths[:1]),
            ),
            note="Commercial retailer/store prediction outputs published with duplicate-protected registry updates.",
        )

        progress.start_stage(13, OPERATIONAL_CYCLE_STAGE_COUNT, "Validate client execution packs")
        progress.detail("action: validate pilot outputs and gold-standard acceptance checks for client-safe publishing")
        with progress.heartbeat(
            "running pilot and gold-standard validation checks",
            heartbeat_seconds=8.0,
            row_count=int(store_prediction_artifacts.row_count),
        ):
            pilot_validation_artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id=run_id,
                as_of_date=settings.as_of_date.isoformat(),
                source_frame=store_download_frame,
                stage11_store_promotion_paths=store_prediction_artifacts.per_store_promotion_csv_paths,
                stage13_review_paths=commercial_publish_artifacts.review_paths,
                stage13_pos_upload_paths=commercial_publish_artifacts.pos_upload_paths,
                stage13_reconciliation_paths=commercial_publish_artifacts.reconciliation_paths,
                artifact_paths=settings.artifacts,
                stage12_publish_status=commercial_publish_artifacts.publish_status,
                stage12_publish_status_reason=commercial_publish_artifacts.publish_status_reason,
                validation_reference_cycle_path="",
            )
        progress.detail(
            f"validation_status: {pilot_validation_artifacts.validation_status}"
        )
        progress.detail(
            f"validation_status_reason: {pilot_validation_artifacts.validation_status_reason}"
        )
        progress.detail(
            f"validation_skip_class: {pilot_validation_artifacts.validation_skip_class}"
        )
        progress.detail(
            f"validation_skip_message: {pilot_validation_artifacts.validation_skip_message}"
        )
        if pilot_validation_artifacts.validation_skipped_flag:
            progress.detail(
                "stage13_skip_message: Stage 13 skipped new-pack validation because no new publications were produced; "
                "prior published pack validation not requested."
            )
        progress.complete_stage(
            row_count=store_prediction_artifacts.row_count,
            file_count=6,
            output_paths=(
                pilot_validation_artifacts.pilot_validation_summary_csv_path,
                pilot_validation_artifacts.pilot_validation_failures_csv_path,
                pilot_validation_artifacts.gold_standard_acceptance_results_csv_path,
                pilot_validation_artifacts.validation_manifest_path,
            ),
            note="Pilot validation and gold-standard acceptance checks passed for client-safe publish readiness.",
        )

        progress.start_stage(14, OPERATIONAL_CYCLE_STAGE_COUNT, "Final manifest write")
        progress.detail("action: write top-level manifest links, local inspection copies, and operator outputs")
        with progress.heartbeat(
            "writing final manifest links and local inspection outputs",
            heartbeat_seconds=8.0,
            row_count=int(len(scoring_artifacts.row_frame.index)),
            file_count=8,
        ):
            decision_surface_csv_path = decision_surface_artifacts.report_paths[
                "promotion_decision_surface"
            ]["csv"]
            inspection_review_packet_csv_path = decision_surface_artifacts.inspection_report_paths[
                "inspection_promotion_review_packet"
            ]["csv"]
            local_inspection_artifacts = write_local_inspection_outputs(
                run_id=run_id,
                as_of_date=settings.as_of_date.isoformat(),
                execution_mode=execution_mode,
                artifact_paths=settings.artifacts,
                nas_store_prediction_csv_path=store_prediction_artifacts.csv_path,
                nas_decision_surface_csv_path=decision_surface_csv_path,
                nas_review_packet_csv_path=inspection_review_packet_csv_path,
                operational_cycle_manifest_path=str(manifest_path),
                operator_log_path=str(settings.artifacts.operator_log_path(run_id)),
                audit_summary_json_path=audit_artifacts.summary_json_path,
                audit_summary_csv_path=audit_artifacts.summary_csv_path,
                operator_summary_json_path=str(settings.artifacts.operator_summary_path(run_id)),
                operator_summary_csv_path=str(settings.artifacts.operator_summary_csv_path(run_id)),
            )

        commercial_outcome = classify_commercial_outcome(
            CommercialOutcomeInput(
                run_completed_successfully_flag=True,
                stage12_publish_status=commercial_publish_artifacts.publish_status,
                stage12_publish_status_reason=commercial_publish_artifacts.publish_status_reason,
                stage12_pos_upload_row_count=int(commercial_publish_artifacts.pos_upload_row_count),
                stage12_candidate_row_count=int(commercial_publish_artifacts.candidate_row_count),
                stage12_duplicate_registry_skip_count=int(
                    commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
                ),
                stage13_validation_status=pilot_validation_artifacts.validation_status,
                stage13_validation_status_reason=pilot_validation_artifacts.validation_status_reason,
                stage13_skip_class=pilot_validation_artifacts.validation_skip_class,
            )
        )
        # BUILD PREMIUM COMMERCIAL DIAGNOSTICS SEAMS
        # Collect stage timings from progress object for publication opportunity timing builder
        stage_timings_map: dict[int, float | None] = {}
        for record in progress._stage_records:
            stage_timings_map[record.stage_number] = record.elapsed_seconds

        # Read store prediction CSV to collect Stage 11 demand classification counts
        store_prediction_frame = pd.read_csv(
            store_prediction_artifacts.master_csv_path, encoding="utf-8"
        )
        stage11_total_rows = int(len(store_prediction_frame.index))
        
        # Count demand evidence classes - defaults for counts
        stage11_order_rows = 0
        stage11_review_rows = 0
        stage11_true_zero_rows = 0
        stage11_cold_start_rows = 0
        stage11_low_nonzero_rows = 0
        stage11_artificial_collapse_rows = 0
        
        if "demand_evidence_class" in store_prediction_frame.columns:
            demand_class_counts = store_prediction_frame[
                "demand_evidence_class"
            ].value_counts(dropna=False)
            # Map actual string values to demand class counts
            for demand_class, count in demand_class_counts.items():
                if demand_class == "true_zero_demand":
                    stage11_true_zero_rows = int(count)
                elif demand_class == "cold_start_new_line":
                    stage11_cold_start_rows = int(count)
                elif demand_class == "low_nonzero_demand":
                    stage11_low_nonzero_rows = int(count)
                elif demand_class == "artificial_collapse":
                    stage11_artificial_collapse_rows = int(count)
                elif demand_class == "healthy_nonzero_demand":
                    stage11_order_rows += int(count)
                # null/missing demand_class = healthy rows publishable as orders
                elif pd.isna(demand_class):
                    stage11_order_rows += int(count)
            
            # Any review-only classification would be flagged separately - default to 0 for now
            stage11_review_rows = 0

        stage12_legitimate_excluded_row_count = _derive_stage12_legitimate_excluded_row_count(
            commercial_publish_artifacts
        )

        # Classify publication opportunity using Stage 11 and Stage 12 real data
        publication_opportunity_input = PublicationOpportunityInput(
            stage11_total_rows=stage11_total_rows,
            stage11_order_rows=stage11_order_rows,
            stage11_review_rows=stage11_review_rows,
            stage11_true_zero_rows=stage11_true_zero_rows,
            stage11_cold_start_rows=stage11_cold_start_rows,
            stage11_low_nonzero_rows=stage11_low_nonzero_rows,
            stage11_artificial_collapse_rows=stage11_artificial_collapse_rows,
            stage12_publish_status=commercial_publish_artifacts.publish_status,
            stage12_publish_status_reason=commercial_publish_artifacts.publish_status_reason,
            stage12_candidate_row_count=int(commercial_publish_artifacts.candidate_row_count),
            stage12_publishable_row_count=int(commercial_publish_artifacts.pos_upload_row_count),
            stage12_review_only_row_count=int(commercial_publish_artifacts.skipped_due_to_review_count),
            stage12_legitimate_excluded_row_count=stage12_legitimate_excluded_row_count,
            stage12_defect_excluded_row_count=int(commercial_publish_artifacts.skipped_due_to_schema_count),
            stage12_duplicate_registry_skip_count=int(
                commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
            ),
        )
        
        publication_opportunity = classify_publication_opportunity(publication_opportunity_input)

        # Build publish reconciliation summary (fail-loud on mismatch)
        try:
            publish_reconciliation_summary = build_publish_reconciliation_summary(
                publication_opportunity_input
            )
        except ValueError as e:
            progress.detail(f"reconciliation_error: {str(e)}")
            publish_reconciliation_summary = None

        # Build commercial stage timing summary
        commercial_stage_timing = build_commercial_stage_timing(
            run_id=run_id,
            stage6_elapsed_seconds=stage_timings_map.get(6),
            stage8_elapsed_seconds=stage_timings_map.get(8),
            stage11_elapsed_seconds=stage_timings_map.get(11),
            stage12_elapsed_seconds=stage_timings_map.get(12),
            stage13_elapsed_seconds=stage_timings_map.get(13),
        )

        # Build duplicate registry skip summary only if NOOP-already-published
        duplicate_registry_skip_summary = None
        if commercial_publish_artifacts.noop_already_published_flag:
            duplicate_registry_skip_summary = build_duplicate_registry_skip_summary(
                skipped_row_count=int(
                    commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
                ),
                unique_store_count=int(commercial_publish_artifacts.stores_published),
                unique_promotion_count=int(
                    commercial_publish_artifacts.promotion_cycles_published
                ),
                unique_sku_count=0,  # Not available in publish artifacts; will be 0 for NOOP
            )

        # Classify commercial freshness and replay safety
        commercial_freshness = classify_commercial_freshness(
            publication_opportunity_class=publication_opportunity.publication_opportunity_class,
            newly_published_row_count=int(commercial_publish_artifacts.pos_upload_row_count),
            duplicate_registry_skip_count=int(
                commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
            ),
            review_only_row_count=int(commercial_publish_artifacts.skipped_due_to_review_count),
            legitimate_zero_row_count=stage12_legitimate_excluded_row_count,
            filtered_out_row_count=int(
                commercial_publish_artifacts.skipped_due_to_schema_count
            ),
            defect_blocked_row_count=int(commercial_publish_artifacts.skipped_due_to_schema_count)
            if "FAIL" in commercial_publish_artifacts.publish_status else 0,
            validation_status=pilot_validation_artifacts.validation_status,
        )

        commercial_replay_safety = classify_replay_safety(
            freshness_class=commercial_freshness.freshness_class,
            commercial_outcome_blocked_by_defect_flag=commercial_outcome.commercial_failure_flag,
            stage12_publish_status=commercial_publish_artifacts.publish_status,
        )

        # Validate freshness/replay-safety consistency
        try:
            validate_freshness_replay_consistency(
                publication_opportunity_class=publication_opportunity.publication_opportunity_class,
                freshness_class=commercial_freshness.freshness_class,
                commercially_new_value_created_flag=commercial_freshness.commercially_new_value_created_flag,
                replay_safety_class=commercial_replay_safety.replay_safety_class,
                safe_to_rerun_without_input_change_flag=commercial_replay_safety.safe_to_rerun_without_input_change_flag,
                stage12_publish_status=commercial_publish_artifacts.publish_status,
                defect_blocked_row_count=int(commercial_publish_artifacts.skipped_due_to_schema_count)
                if "FAIL" in commercial_publish_artifacts.publish_status else 0,
            )
        except ValueError as e:
            progress.detail(f"freshness_replay_consistency_error: {str(e)}")
            # Fail loud on consistency violations
            raise

        # Build publication freshness diagnostic
        publication_freshness_diagnostic_new = build_publication_freshness_diagnostic(
            freshness_class=commercial_freshness.freshness_class,
            commercially_new_value_created_flag=commercial_freshness.commercially_new_value_created_flag,
            duplicate_registry_skip_count=int(
                commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
            ),
            newly_published_row_count=int(commercial_publish_artifacts.pos_upload_row_count),
            review_only_row_count=int(commercial_publish_artifacts.skipped_due_to_review_count),
            legitimate_zero_row_count=stage12_legitimate_excluded_row_count,
            filtered_out_row_count=int(
                commercial_publish_artifacts.skipped_due_to_schema_count
            ),
            defect_blocked_row_count=int(commercial_publish_artifacts.skipped_due_to_schema_count)
            if "FAIL" in commercial_publish_artifacts.publish_status else 0,
            replay_safety_class=commercial_replay_safety.replay_safety_class,
            replay_safety_reason=commercial_replay_safety.replay_safety_reason,
            first_publication_date_if_any=None,  # Not available in publish artifacts
            last_publication_date_if_any=None,  # Not available in publish artifacts
        )

        # Build authoritative incremental commercial delta intelligence
        commercial_delta_intelligence = build_commercial_delta_intelligence(
            run_id=run_id,
            as_of_date=settings.as_of_date.isoformat(),
            manifests_root=settings.artifacts.manifests_root,
            current_store_prediction_csv_path=store_prediction_artifacts.master_csv_path,
            current_publishable_row_count=int(commercial_publish_artifacts.pos_upload_row_count),
            current_stage12_publish_status=commercial_publish_artifacts.publish_status,
            current_commercial_failure_flag=bool(commercial_outcome.commercial_failure_flag),
        )
        commercial_delta_summary = commercial_delta_intelligence.summary
        commercial_delta_top_changes = commercial_delta_intelligence.top_changes
        commercial_delta_store_summary = commercial_delta_intelligence.store_summary

        commercial_change_explainability = build_commercial_change_explainability_artifacts(
            run_id=run_id,
            as_of_date=settings.as_of_date.isoformat(),
            manifests_root=settings.artifacts.manifests_root,
            current_store_prediction_csv_path=store_prediction_artifacts.master_csv_path,
            current_commercial_outcome_class=commercial_outcome.commercial_outcome_class,
            current_freshness_class=commercial_freshness.freshness_class,
            current_delta_class=commercial_delta_summary.delta_class,
            duplicate_registry_skip_count=int(
                commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
            ),
            prior_cycle_run_id=commercial_delta_summary.prior_cycle_run_id,
        )
        commercial_change_explanations = commercial_change_explainability.explanations
        commercial_priority_queue = commercial_change_explainability.priority_queue
        commercial_action_summary = commercial_change_explainability.action_summary

        commercial_outcome_attribution = build_commercial_outcome_attribution_artifacts(
            as_of_date=settings.as_of_date.isoformat(),
            current_store_prediction_csv_path=store_prediction_artifacts.master_csv_path,
            commercial_change_explanations=commercial_change_explanations,
            current_freshness_class=commercial_freshness.freshness_class,
            current_commercial_outcome_class=commercial_outcome.commercial_outcome_class,
            duplicate_registry_skip_count=int(
                commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
            ),
        )
        commercial_outcome_attribution_frame = commercial_outcome_attribution.attribution
        recommendation_effectiveness_summary = (
            commercial_outcome_attribution.recommendation_effectiveness_summary
        )
        recommendation_effectiveness_by_reason = (
            commercial_outcome_attribution.recommendation_effectiveness_by_reason
        )
        recommendation_learning_priority_queue = (
            commercial_outcome_attribution.recommendation_learning_priority_queue
        )

        commercial_policy_calibration = build_commercial_policy_calibration_artifacts(
            attribution=commercial_outcome_attribution_frame,
            current_commercial_outcome_class=commercial_outcome.commercial_outcome_class,
        )
        commercial_policy_calibration_summary = commercial_policy_calibration.summary
        commercial_policy_calibration_by_segment = commercial_policy_calibration.by_segment
        commercial_policy_watchlist = commercial_policy_calibration.watchlist

        commercial_policy_simulation = build_commercial_policy_simulation_artifacts(
            attribution=commercial_outcome_attribution_frame,
            calibration_summary=commercial_policy_calibration_summary.to_dict(),
            current_commercial_outcome_class=commercial_outcome.commercial_outcome_class,
        )
        commercial_policy_simulation_summary = commercial_policy_simulation.summary
        commercial_policy_simulation_by_segment = commercial_policy_simulation.by_segment
        commercial_policy_simulation_watchlist = commercial_policy_simulation.watchlist

        commercial_action_instruction = build_commercial_action_instruction_artifacts(
            run_id=run_id,
            current_store_prediction_csv_path=store_prediction_artifacts.master_csv_path,
            commercial_change_explanations=commercial_change_explanations,
            commercial_outcome_attribution=commercial_outcome_attribution_frame,
            commercial_delta_top_changes=commercial_delta_top_changes,
            commercial_delta_store_summary=commercial_delta_store_summary,
            commercial_delta_summary=commercial_delta_summary.to_dict(),
            commercial_policy_calibration_summary=commercial_policy_calibration_summary.to_dict(),
            commercial_policy_calibration_by_segment=commercial_policy_calibration_by_segment,
            commercial_policy_watchlist=commercial_policy_watchlist,
            commercial_policy_simulation_summary=commercial_policy_simulation_summary.to_dict(),
            commercial_policy_simulation_by_segment=commercial_policy_simulation_by_segment,
            commercial_policy_simulation_watchlist=commercial_policy_simulation_watchlist,
            commercial_outcome_class=commercial_outcome.commercial_outcome_class,
            current_freshness_class=commercial_freshness.freshness_class,
            current_commercial_failure_flag=bool(commercial_outcome.commercial_failure_flag),
        )
        commercial_action_instruction_summary = commercial_action_instruction.summary

        top_operator_action_class = (
            str(commercial_priority_queue.iloc[0]["operator_action_class"])
            if not commercial_priority_queue.empty
            else "NONE"
        )
        top_operator_priority_band = (
            str(commercial_priority_queue.iloc[0]["operator_priority_band"])
            if not commercial_priority_queue.empty
            else "NONE"
        )

        commercial_action_instruction_summary = commercial_action_instruction.summary

        # Build commercial operator brief
        commercial_operator_brief = build_commercial_operator_brief(
            run_id=run_id,
            as_of_date=settings.as_of_date.isoformat(),
            commercial_outcome_class=commercial_outcome.commercial_outcome_class,
            commercial_outcome_message=commercial_outcome.commercial_outcome_message,
            publication_opportunity_class=publication_opportunity.publication_opportunity_class,
            publication_opportunity_message=publication_opportunity.publication_opportunity_message,
            stage12_publish_status=commercial_publish_artifacts.publish_status,
            stage12_publish_status_reason=commercial_publish_artifacts.publish_status_reason,
            stage13_skip_class=pilot_validation_artifacts.validation_skip_class,
            stage11_total_rows=stage11_total_rows,
            stage12_candidate_row_count=int(commercial_publish_artifacts.candidate_row_count),
            stage12_publishable_row_count=int(commercial_publish_artifacts.pos_upload_row_count),
            stage12_duplicate_registry_skip_count=int(
                commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
            ),
            freshness_class=commercial_freshness.freshness_class,
            freshness_reason=commercial_freshness.freshness_reason,
            freshness_message=commercial_freshness.freshness_message,
            commercially_new_value_created_flag=commercial_freshness.commercially_new_value_created_flag,
            replay_safety_class=commercial_replay_safety.replay_safety_class,
            replay_safety_reason=commercial_replay_safety.replay_safety_reason,
            exact_rerun_expected_outcome=commercial_replay_safety.exact_rerun_expected_outcome,
            operator_guidance_message_replay=commercial_replay_safety.operator_guidance_message,
            delta_class=commercial_delta_summary.delta_class,
            delta_reason=commercial_delta_summary.delta_reason,
            delta_message=commercial_delta_summary.delta_message,
            comparable_prior_cycle_found_flag=commercial_delta_summary.comparable_prior_cycle_found_flag,
            comparable_prior_cycle_run_id=commercial_delta_summary.prior_cycle_run_id,
            materiality_class=commercial_delta_summary.materiality_class,
            materiality_reason=commercial_delta_summary.materiality_reason,
            materially_changed_flag=commercial_delta_summary.materially_changed_flag,
            operator_attention_recommended_flag=commercial_delta_summary.operator_attention_recommended_flag,
            changed_store_count=commercial_delta_summary.changed_store_count,
            changed_promotion_count=commercial_delta_summary.changed_promotion_count,
            changed_store_sku_count=commercial_delta_summary.changed_store_sku_count,
            action_publish_now_count=commercial_action_summary.action_publish_now_count,
            action_review_now_count=commercial_action_summary.action_review_now_count,
            action_monitor_count=commercial_action_summary.action_monitor_count,
            action_no_action_duplicate_count=commercial_action_summary.action_no_action_duplicate_count,
            action_no_action_true_zero_count=commercial_action_summary.action_no_action_true_zero_count,
            action_investigate_defect_count=commercial_action_summary.action_investigate_defect_count,
            top_operator_action_class=top_operator_action_class,
            top_operator_priority_band=top_operator_priority_band,
            priority_queue_preview_lines=[
                f"{idx + 1}. Store {str(row['store_number'])} SKU {str(row['sku_number'])} | {str(row['operator_action_class'])} | {str(row['operator_priority_band'])} | {str(row['row_change_reason_code'])}"
                for idx, (_, row) in enumerate(commercial_priority_queue.head(10).iterrows())
            ],
            attribution_ready_count=recommendation_effectiveness_summary.attribution_ready_count,
            attribution_not_yet_mature_count=recommendation_effectiveness_summary.attribution_not_yet_mature_count,
            blocked_missing_outcome_data_count=recommendation_effectiveness_summary.blocked_missing_outcome_data_count,
            effective_strong_count=recommendation_effectiveness_summary.effective_strong_count,
            effective_moderate_count=recommendation_effectiveness_summary.effective_moderate_count,
            neutral_count=recommendation_effectiveness_summary.neutral_count,
            ineffective_count=recommendation_effectiveness_summary.ineffective_count,
            harmful_count=recommendation_effectiveness_summary.harmful_count,
            inconclusive_count=recommendation_effectiveness_summary.inconclusive_count,
            average_effectiveness_score=recommendation_effectiveness_summary.average_effectiveness_score,
            publish_now_average_effectiveness_score=recommendation_effectiveness_summary.publish_now_average_effectiveness_score,
            review_now_average_effectiveness_score=recommendation_effectiveness_summary.review_now_average_effectiveness_score,
            commercial_learning_signal_strength_class=recommendation_effectiveness_summary.commercial_learning_signal_strength_class,
            learning_priority_preview_lines=[
                f"{idx + 1}. Store {str(row['store_number'])} SKU {str(row['sku_number'])} | {str(row['recommendation_effectiveness_class'])} | {str(row['attribution_confidence_class'])} | score={str(row['recommendation_effectiveness_score'])}"
                for idx, (_, row) in enumerate(recommendation_learning_priority_queue.head(10).iterrows())
            ],
            policy_signal_class=commercial_policy_calibration_summary.policy_signal_class,
            calibration_readiness_class=commercial_policy_calibration_summary.calibration_readiness_class,
            threshold_direction_class=commercial_policy_calibration_summary.threshold_direction_class,
            commercial_policy_confidence_class=commercial_policy_calibration_summary.confidence_class,
            policy_tighten_preview_lines=[
                f"{idx + 1}. {str(row['segment_type'])}={str(row['segment_value'])} | harmful_rate={str(row['harmful_rate'])} | evidence={str(row['evidence_row_count'])}"
                for idx, (_, row) in enumerate(
                    commercial_policy_calibration_by_segment[
                        commercial_policy_calibration_by_segment["threshold_direction_class"]
                        == "TIGHTEN_PUBLISH_POLICY"
                    ]
                    .head(10)
                    .iterrows()
                )
            ],
            policy_loosen_preview_lines=[
                f"{idx + 1}. {str(row['segment_type'])}={str(row['segment_value'])} | effective_rate={str(row['effective_rate'])} | evidence={str(row['evidence_row_count'])}"
                for idx, (_, row) in enumerate(
                    commercial_policy_calibration_by_segment[
                        commercial_policy_calibration_by_segment["threshold_direction_class"]
                        == "LOOSEN_PUBLISH_POLICY"
                    ]
                    .head(10)
                    .iterrows()
                )
            ],
            policy_hold_preview_lines=[
                f"{idx + 1}. {str(row['segment_type'])}={str(row['segment_value'])} | signal={str(row['signal_class'])} | evidence={str(row['evidence_row_count'])}"
                for idx, (_, row) in enumerate(
                    commercial_policy_calibration_by_segment[
                        commercial_policy_calibration_by_segment["threshold_direction_class"]
                        == "HOLD_POLICY"
                    ]
                    .head(10)
                    .iterrows()
                )
            ],
            policy_watchlist_preview_lines=[
                f"{idx + 1}. {str(row['segment_type'])}={str(row['segment_value'])} | reason={str(row['watch_reason'])} | harmful_rate={str(row['harmful_rate'])}"
                for idx, (_, row) in enumerate(commercial_policy_watchlist.head(10).iterrows())
            ],
            simulation_readiness_class=commercial_policy_simulation_summary.simulation_readiness_class,
            simulated_policy_direction_class=commercial_policy_simulation_summary.simulated_policy_direction_class,
            simulated_materiality_class=commercial_policy_simulation_summary.simulated_materiality_class,
            simulated_risk_class=commercial_policy_simulation_summary.simulated_risk_class,
            baseline_publish_row_count=commercial_policy_simulation_summary.baseline_publish_row_count,
            simulated_publish_row_count=commercial_policy_simulation_summary.simulated_publish_row_count,
            net_publish_delta=commercial_policy_simulation_summary.net_publish_delta,
            baseline_review_row_count=commercial_policy_simulation_summary.baseline_review_row_count,
            simulated_review_row_count=commercial_policy_simulation_summary.simulated_review_row_count,
            net_review_delta=commercial_policy_simulation_summary.net_review_delta,
            baseline_excluded_row_count=commercial_policy_simulation_summary.baseline_excluded_row_count,
            simulated_excluded_row_count=commercial_policy_simulation_summary.simulated_excluded_row_count,
            net_excluded_delta=commercial_policy_simulation_summary.net_excluded_delta,
            simulated_affected_row_count=commercial_policy_simulation_summary.affected_row_count,
            simulated_affected_store_count=commercial_policy_simulation_summary.affected_store_count,
            simulated_affected_promotion_count=commercial_policy_simulation_summary.affected_promotion_count,
            simulation_winners_preview_lines=[
                f"{idx + 1}. {str(row['segment_type'])}={str(row['segment_value'])} | net_publish_delta={str(row['net_publish_delta'])} | affected_rows={str(row['affected_row_count'])}"
                for idx, (_, row) in enumerate(
                    commercial_policy_simulation_by_segment[
                        commercial_policy_simulation_by_segment["net_publish_delta"] > 0
                    ]
                    .sort_values(by=["net_publish_delta", "affected_row_count"], ascending=[False, False])
                    .head(10)
                    .iterrows()
                )
            ],
            simulation_risks_preview_lines=[
                f"{idx + 1}. {str(row['segment_type'])}={str(row['segment_value'])} | risk={str(row['simulated_risk_class'])} | net_publish_delta={str(row['net_publish_delta'])} | affected_rows={str(row['affected_row_count'])}"
                for idx, (_, row) in enumerate(
                    commercial_policy_simulation_by_segment[
                        (commercial_policy_simulation_by_segment["simulated_risk_class"] == "SIMULATION_HIGH_RISK")
                        | (commercial_policy_simulation_by_segment["simulated_risk_class"] == "SIMULATION_MODERATE_RISK")
                        | (commercial_policy_simulation_by_segment["net_publish_delta"] < 0)
                    ]
                    .sort_values(by=["affected_row_count", "net_publish_delta"], ascending=[False, True])
                    .head(10)
                    .iterrows()
                )
            ],
            simulation_watchlist_preview_lines=[
                f"{idx + 1}. {str(row['segment_type'])}={str(row['segment_value'])} | reason={str(row['watch_reason'])} | net_publish_delta={str(row['net_publish_delta'])} | affected_rows={str(row['affected_row_count'])}"
                for idx, (_, row) in enumerate(commercial_policy_simulation_watchlist.head(10).iterrows())
            ],
            action_instruction_readiness_class=commercial_action_instruction_summary.action_instruction_readiness_class,
            action_instruction_readiness_reason=commercial_action_instruction_summary.action_instruction_readiness_reason,
            immediate_priorities_preview_lines=[
                f"#{int(row['action_priority_rank'])} {row['action_class']} | owner={row['action_owner_class']} | attention={row['operator_attention_class']} | {row['action_reason']}"
                for _, row in commercial_action_instruction.priority_queue[
                    commercial_action_instruction.priority_queue["operator_attention_class"] == "ATTENTION_IMMEDIATE"
                ].head(10).iterrows()
            ],
            top_operator_action_preview_lines=[
                f"#{int(row['action_priority_rank'])} {row['action_class']} | owner={row['action_owner_class']} | store={row['linked_store_number']} | promotion={row['linked_promotion_id']}"
                for _, row in commercial_action_instruction.priority_queue[
                    commercial_action_instruction.priority_queue["action_owner_class"] == "OPERATOR"
                ].head(10).iterrows()
            ],
            top_model_owner_action_preview_lines=[
                f"#{int(row['action_priority_rank'])} {row['action_class']} | owner={row['action_owner_class']} | store={row['linked_store_number']} | promotion={row['linked_promotion_id']}"
                for _, row in commercial_action_instruction.priority_queue[
                    commercial_action_instruction.priority_queue["action_owner_class"] == "MODEL_OWNER"
                ].head(10).iterrows()
            ],
            action_queue_preview_lines=[
                f"#{int(row['action_priority_rank'])} {row['action_class']} | owner={row['action_owner_class']} | attention={row['operator_attention_class']} | {row['action_reason']}"
                for _, row in commercial_action_instruction.priority_queue.head(10).iterrows()
            ],
        )

        # Write new governed artifacts
        publish_reconciliation_summary_path = (
            settings.artifacts.publish_reconciliation_summary_path(run_id)
        )
        if publish_reconciliation_summary is not None:
            publish_reconciliation_summary_path.parent.mkdir(parents=True, exist_ok=True)
            publish_reconciliation_summary_path.write_text(
                json.dumps(
                    publish_reconciliation_summary.to_dict(), indent=2, sort_keys=True
                ),
                encoding="utf-8",
            )

        commercial_stage_timing_summary_path = (
            settings.artifacts.commercial_stage_timing_summary_path(run_id)
        )
        commercial_stage_timing_summary_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_stage_timing_summary_path.write_text(
            json.dumps(
                commercial_stage_timing.to_dict(), indent=2, sort_keys=True
            ),
            encoding="utf-8",
        )

        duplicate_registry_skip_summary_path = None
        if duplicate_registry_skip_summary is not None:
            duplicate_registry_skip_summary_path = (
                settings.artifacts.duplicate_registry_skip_summary_path(run_id)
            )
            duplicate_registry_skip_summary_path.parent.mkdir(parents=True, exist_ok=True)
            duplicate_registry_skip_summary_path.write_text(
                json.dumps(
                    duplicate_registry_skip_summary.to_dict(), indent=2, sort_keys=True
                ),
                encoding="utf-8",
            )

        # Write publication freshness diagnostic
        publication_freshness_diagnostic_new_path = (
            settings.artifacts.publication_freshness_diagnostic_path(run_id)
        )
        publication_freshness_diagnostic_new_path.parent.mkdir(parents=True, exist_ok=True)
        publication_freshness_diagnostic_new_path.write_text(
            json.dumps(
                publication_freshness_diagnostic_new.to_dict(), indent=2, sort_keys=True
            ),
            encoding="utf-8",
        )

        # Write commercial replay safety summary
        commercial_replay_safety_summary_path = (
            settings.artifacts.commercial_replay_safety_summary_path(run_id)
        )
        commercial_replay_safety_summary_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_replay_safety_summary_path.write_text(
            json.dumps(
                commercial_replay_safety.to_dict(), indent=2, sort_keys=True
            ),
            encoding="utf-8",
        )

        commercial_delta_summary_path = settings.artifacts.commercial_delta_summary_path(run_id)
        commercial_delta_summary_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_delta_summary_path.write_text(
            json.dumps(commercial_delta_summary.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        commercial_delta_top_changes_csv_path = settings.artifacts.commercial_delta_top_changes_csv_path(run_id)
        commercial_delta_top_changes_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_delta_top_changes.to_csv(
            commercial_delta_top_changes_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_delta_store_summary_csv_path = settings.artifacts.commercial_delta_store_summary_csv_path(run_id)
        commercial_delta_store_summary_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_delta_store_summary.to_csv(
            commercial_delta_store_summary_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_change_explanations_csv_path = settings.artifacts.commercial_change_explanations_csv_path(run_id)
        commercial_change_explanations_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_change_explanations.to_csv(
            commercial_change_explanations_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_priority_queue_csv_path = settings.artifacts.commercial_priority_queue_csv_path(run_id)
        commercial_priority_queue_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_priority_queue.to_csv(
            commercial_priority_queue_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_action_summary_path = settings.artifacts.commercial_action_summary_path(run_id)
        commercial_action_summary_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_action_summary_path.write_text(
            json.dumps(commercial_action_summary.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        commercial_outcome_attribution_csv_path = settings.artifacts.commercial_outcome_attribution_csv_path(run_id)
        commercial_outcome_attribution_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_outcome_attribution_frame.to_csv(
            commercial_outcome_attribution_csv_path,
            index=False,
            encoding="utf-8",
        )

        recommendation_effectiveness_summary_path = settings.artifacts.recommendation_effectiveness_summary_path(run_id)
        recommendation_effectiveness_summary_path.parent.mkdir(parents=True, exist_ok=True)
        recommendation_effectiveness_summary_path.write_text(
            json.dumps(recommendation_effectiveness_summary.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        recommendation_effectiveness_by_reason_csv_path = settings.artifacts.recommendation_effectiveness_by_reason_csv_path(run_id)
        recommendation_effectiveness_by_reason_csv_path.parent.mkdir(parents=True, exist_ok=True)
        recommendation_effectiveness_by_reason.to_csv(
            recommendation_effectiveness_by_reason_csv_path,
            index=False,
            encoding="utf-8",
        )

        recommendation_learning_priority_queue_csv_path = settings.artifacts.recommendation_learning_priority_queue_csv_path(run_id)
        recommendation_learning_priority_queue_csv_path.parent.mkdir(parents=True, exist_ok=True)
        recommendation_learning_priority_queue.to_csv(
            recommendation_learning_priority_queue_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_policy_calibration_summary_path = settings.artifacts.commercial_policy_calibration_summary_path(run_id)
        commercial_policy_calibration_summary_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_policy_calibration_summary_path.write_text(
            json.dumps(commercial_policy_calibration_summary.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        commercial_policy_calibration_by_segment_csv_path = settings.artifacts.commercial_policy_calibration_by_segment_csv_path(run_id)
        commercial_policy_calibration_by_segment_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_policy_calibration_by_segment.to_csv(
            commercial_policy_calibration_by_segment_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_policy_watchlist_csv_path = settings.artifacts.commercial_policy_watchlist_csv_path(run_id)
        commercial_policy_watchlist_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_policy_watchlist.to_csv(
            commercial_policy_watchlist_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_policy_calibration_brief_path = settings.artifacts.commercial_policy_calibration_brief_path(run_id)
        commercial_policy_calibration_brief_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_policy_calibration_brief_path.write_text(
            commercial_policy_calibration.calibration_brief_markdown,
            encoding="utf-8",
        )

        commercial_policy_simulation_summary_path = settings.artifacts.commercial_policy_simulation_summary_path(run_id)
        commercial_policy_simulation_summary_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_policy_simulation_summary_path.write_text(
            json.dumps(commercial_policy_simulation_summary.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        commercial_policy_simulation_by_segment_csv_path = settings.artifacts.commercial_policy_simulation_by_segment_csv_path(run_id)
        commercial_policy_simulation_by_segment_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_policy_simulation_by_segment.to_csv(
            commercial_policy_simulation_by_segment_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_policy_simulation_watchlist_csv_path = settings.artifacts.commercial_policy_simulation_watchlist_csv_path(run_id)
        commercial_policy_simulation_watchlist_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_policy_simulation_watchlist.to_csv(
            commercial_policy_simulation_watchlist_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_policy_simulation_brief_path = settings.artifacts.commercial_policy_simulation_brief_path(run_id)
        commercial_policy_simulation_brief_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_policy_simulation_brief_path.write_text(
            commercial_policy_simulation.simulation_brief_markdown,
            encoding="utf-8",
        )

        commercial_action_instruction_summary_path = settings.artifacts.commercial_action_instruction_summary_path(run_id)
        commercial_action_instruction_summary_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_action_instruction_summary_path.write_text(
            json.dumps(commercial_action_instruction_summary.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        commercial_action_priority_queue_csv_path = settings.artifacts.commercial_action_priority_queue_csv_path(run_id)
        commercial_action_priority_queue_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_action_instruction.priority_queue.to_csv(
            commercial_action_priority_queue_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_action_by_segment_csv_path = settings.artifacts.commercial_action_by_segment_csv_path(run_id)
        commercial_action_by_segment_csv_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_action_instruction.by_segment.to_csv(
            commercial_action_by_segment_csv_path,
            index=False,
            encoding="utf-8",
        )

        commercial_action_instruction_brief_path = settings.artifacts.commercial_action_instruction_brief_path(run_id)
        commercial_action_instruction_brief_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_action_instruction_brief_path.write_text(
            commercial_action_instruction.brief_markdown,
            encoding="utf-8",
        )

        top_operator_action_class = commercial_action_instruction_summary.top_operator_action_class
        top_model_owner_action_class = commercial_action_instruction_summary.top_model_owner_action_class

        commercial_operator_brief_path = (
            settings.artifacts.commercial_operator_brief_path(run_id)
        )
        commercial_operator_brief_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_operator_brief_path.write_text(
            commercial_operator_brief, encoding="utf-8"
        )

        commercial_run_outcome_summary_path = settings.artifacts.commercial_run_outcome_summary_path(run_id)
        commercial_run_outcome_summary_path.parent.mkdir(parents=True, exist_ok=True)
        commercial_run_outcome_summary_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "as_of_date": settings.as_of_date.isoformat(),
                    "proof_mode_flag": bool(proof_mode),
                    "highest_stage_reached": 14,
                    "completed_successfully_flag": True,
                    "commercial_outcome_class": commercial_outcome.commercial_outcome_class,
                    "commercial_outcome_reason": commercial_outcome.commercial_outcome_reason,
                    "commercial_outcome_message": commercial_outcome.commercial_outcome_message,
                    "publication_opportunity_class": publication_opportunity.publication_opportunity_class,
                    "publication_opportunity_reason": publication_opportunity.publication_opportunity_reason,
                    "publication_opportunity_message": publication_opportunity.publication_opportunity_message,
                    "stage11_row_count": int(store_prediction_artifacts.row_count),
                    "stage12_candidate_row_count": int(commercial_publish_artifacts.candidate_row_count),
                    "stage12_pos_upload_row_count": int(commercial_publish_artifacts.pos_upload_row_count),
                    "stage12_excluded_row_count": int(commercial_publish_artifacts.pos_excluded_row_count),
                    "stage12_duplicate_registry_skip_count": int(
                        commercial_publish_artifacts.skipped_due_to_registry_duplicate_count
                    ),
                    "validation_status": pilot_validation_artifacts.validation_status,
                    "validation_status_reason": pilot_validation_artifacts.validation_status_reason,
                    "operator_summary_json_path": str(settings.artifacts.operator_summary_path(run_id)),
                    "store_prediction_download_manifest_path": store_prediction_artifacts.manifest_path,
                    "publication_summary_csv_path": commercial_publish_artifacts.publication_summary_path,
                    "validation_manifest_path": pilot_validation_artifacts.validation_manifest_path,
                    "decision_surface_manifest_path": decision_surface_artifacts.decision_surface_manifest_path,
                    "publish_reconciliation_summary_path": (
                        str(publish_reconciliation_summary_path)
                        if publish_reconciliation_summary is not None
                        else None
                    ),
                    "commercial_stage_timing_summary_path": str(
                        commercial_stage_timing_summary_path
                    ),
                    "duplicate_registry_skip_summary_path": (
                        str(duplicate_registry_skip_summary_path)
                        if duplicate_registry_skip_summary_path is not None
                        else None
                    ),
                    "commercial_freshness_class": commercial_freshness.freshness_class,
                    "commercial_freshness_reason": commercial_freshness.freshness_reason,
                    "commercial_new_value_created_flag": commercial_freshness.commercially_new_value_created_flag,
                    "commercial_replay_safety_class": commercial_replay_safety.replay_safety_class,
                    "commercial_replay_safety_reason": commercial_replay_safety.replay_safety_reason,
                    "commercial_replay_safe_without_input_change_flag": commercial_replay_safety.safe_to_rerun_without_input_change_flag,
                    "publication_freshness_diagnostic_path": str(
                        publication_freshness_diagnostic_new_path
                    ),
                    "commercial_replay_safety_summary_path": str(
                        commercial_replay_safety_summary_path
                    ),
                    "commercial_delta_class": commercial_delta_summary.delta_class,
                    "commercial_delta_reason": commercial_delta_summary.delta_reason,
                    "commercial_materiality_class": commercial_delta_summary.materiality_class,
                    "commercial_materiality_reason": commercial_delta_summary.materiality_reason,
                    "commercial_materially_changed_flag": commercial_delta_summary.materially_changed_flag,
                    "commercial_operator_attention_recommended_flag": commercial_delta_summary.operator_attention_recommended_flag,
                    "comparable_prior_cycle_found_flag": commercial_delta_summary.comparable_prior_cycle_found_flag,
                    "comparable_prior_cycle_run_id": commercial_delta_summary.prior_cycle_run_id,
                    "commercial_delta_summary_path": str(commercial_delta_summary_path),
                    "commercial_delta_top_changes_csv_path": str(commercial_delta_top_changes_csv_path),
                    "commercial_delta_store_summary_csv_path": str(commercial_delta_store_summary_csv_path),
                    "commercial_change_explanations_csv_path": str(commercial_change_explanations_csv_path),
                    "commercial_priority_queue_csv_path": str(commercial_priority_queue_csv_path),
                    "commercial_action_summary_path": str(commercial_action_summary_path),
                    "commercial_top_operator_action_class": top_operator_action_class,
                    "commercial_top_operator_priority_band": top_operator_priority_band,
                    "commercial_review_now_count": commercial_action_summary.action_review_now_count,
                    "commercial_publish_now_count": commercial_action_summary.action_publish_now_count,
                    "commercial_defect_action_count": commercial_action_summary.action_investigate_defect_count,
                    "commercial_outcome_attribution_csv_path": str(commercial_outcome_attribution_csv_path),
                    "recommendation_effectiveness_summary_path": str(recommendation_effectiveness_summary_path),
                    "recommendation_effectiveness_by_reason_csv_path": str(recommendation_effectiveness_by_reason_csv_path),
                    "recommendation_learning_priority_queue_csv_path": str(recommendation_learning_priority_queue_csv_path),
                    "attribution_ready_count": recommendation_effectiveness_summary.attribution_ready_count,
                    "attribution_effective_count": recommendation_effectiveness_summary.attribution_effective_count,
                    "attribution_harmful_count": recommendation_effectiveness_summary.attribution_harmful_count,
                    "attribution_inconclusive_count": recommendation_effectiveness_summary.attribution_inconclusive_count,
                    "commercial_learning_signal_strength_class": recommendation_effectiveness_summary.commercial_learning_signal_strength_class,
                    "commercial_policy_calibration_summary_path": str(commercial_policy_calibration_summary_path),
                    "commercial_policy_calibration_by_segment_csv_path": str(commercial_policy_calibration_by_segment_csv_path),
                    "commercial_policy_watchlist_csv_path": str(commercial_policy_watchlist_csv_path),
                    "commercial_policy_calibration_brief_path": str(commercial_policy_calibration_brief_path),
                    "policy_signal_class": commercial_policy_calibration_summary.policy_signal_class,
                    "calibration_readiness_class": commercial_policy_calibration_summary.calibration_readiness_class,
                    "threshold_direction_class": commercial_policy_calibration_summary.threshold_direction_class,
                    "commercial_policy_confidence_class": commercial_policy_calibration_summary.confidence_class,
                    "commercial_policy_simulation_summary_path": str(commercial_policy_simulation_summary_path),
                    "commercial_policy_simulation_by_segment_csv_path": str(commercial_policy_simulation_by_segment_csv_path),
                    "commercial_policy_simulation_watchlist_csv_path": str(commercial_policy_simulation_watchlist_csv_path),
                    "commercial_policy_simulation_brief_path": str(commercial_policy_simulation_brief_path),
                    "commercial_action_instruction_summary_path": str(commercial_action_instruction_summary_path),
                    "commercial_action_priority_queue_csv_path": str(commercial_action_priority_queue_csv_path),
                    "commercial_action_by_segment_csv_path": str(commercial_action_by_segment_csv_path),
                    "commercial_action_instruction_brief_path": str(commercial_action_instruction_brief_path),
                    "commercial_action_instruction_readiness_class": commercial_action_instruction_summary.action_instruction_readiness_class,
                    "commercial_action_instruction_readiness_reason": commercial_action_instruction_summary.action_instruction_readiness_reason,
                    "commercial_top_model_owner_action_class": top_model_owner_action_class,
                    "action_instruction_readiness_class": commercial_action_instruction_summary.action_instruction_readiness_class,
                    "top_operator_action_class": commercial_action_instruction_summary.top_operator_action_class,
                    "top_model_owner_action_class": commercial_action_instruction_summary.top_model_owner_action_class,
                    "operator_attention_class": commercial_action_instruction_summary.operator_attention_class,
                    "action_pack_materiality_class": commercial_action_instruction_summary.action_pack_materiality_class,
                    "commercial_action_instruction": commercial_action_instruction_summary.to_dict(),
                    "simulation_readiness_class": commercial_policy_simulation_summary.simulation_readiness_class,
                    "simulated_policy_direction_class": commercial_policy_simulation_summary.simulated_policy_direction_class,
                    "simulated_materiality_class": commercial_policy_simulation_summary.simulated_materiality_class,
                    "simulated_risk_class": commercial_policy_simulation_summary.simulated_risk_class,
                    "simulation_operator_review_recommended_flag": commercial_policy_simulation_summary.operator_review_recommended_flag,
                    "simulation_model_owner_review_recommended_flag": commercial_policy_simulation_summary.model_owner_review_recommended_flag,
                    "simulation_net_publish_delta": commercial_policy_simulation_summary.net_publish_delta,
                    "simulation_affected_row_count": commercial_policy_simulation_summary.affected_row_count,
                    "commercial_operator_brief_path": str(commercial_operator_brief_path),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        manifest_payload["store_outputs"] = {
            "user_facing_prediction_csv_path": store_prediction_artifacts.csv_path,
            "user_facing_prediction_csv_paths": list(
                store_prediction_artifacts.per_store_promotion_csv_paths
            ),
            "per_store_summary_csv_paths": list(store_prediction_artifacts.per_store_csv_paths),
            "internal_master_csv_path": store_prediction_artifacts.master_csv_path,
            "master_csv_path": store_prediction_artifacts.master_csv_path,
            "csv_path": store_prediction_artifacts.csv_path,
            "per_store_csv_paths": list(store_prediction_artifacts.per_store_csv_paths),
            "per_store_promotion_csv_paths": list(
                store_prediction_artifacts.per_store_promotion_csv_paths
            ),
            "manifest_csv_path": store_prediction_artifacts.manifest_csv_path,
            "manifest_path": store_prediction_artifacts.manifest_path,
            "reconciliation_csv_path": store_prediction_artifacts.reconciliation_csv_path,
            "row_count": store_prediction_artifacts.row_count,
            "local_store_prediction_csv_path": (
                local_inspection_artifacts.store_prediction_csv_path
                if local_inspection_artifacts is not None
                else None
            ),
        }
        manifest_payload["commercial_execution_outputs"] = {
            "prediction_registry_path": commercial_publish_artifacts.prediction_registry_path,
            "store_cycle_manifest_paths": list(commercial_publish_artifacts.store_cycle_manifest_paths),
            "pos_upload_paths": list(commercial_publish_artifacts.pos_upload_paths),
            "review_paths": list(commercial_publish_artifacts.review_paths),
            "summary_paths": list(commercial_publish_artifacts.summary_paths),
            "reconciliation_paths": list(commercial_publish_artifacts.reconciliation_paths),
            "publication_summary_path": commercial_publish_artifacts.publication_summary_path,
            "diagnostics_paths": list(commercial_publish_artifacts.diagnostics_paths),
            "skipped_paths": list(commercial_publish_artifacts.skipped_paths),
            "stores_published": commercial_publish_artifacts.stores_published,
            "promotion_predictions_published": commercial_publish_artifacts.promotion_cycles_published,
            "pos_upload_row_count": commercial_publish_artifacts.pos_upload_row_count,
            "pos_excluded_row_count": commercial_publish_artifacts.pos_excluded_row_count,
            "candidate_row_count": commercial_publish_artifacts.candidate_row_count,
            "pos_candidate_row_count": commercial_publish_artifacts.pos_candidate_row_count,
            "publish_status": commercial_publish_artifacts.publish_status,
            "publish_status_reason": commercial_publish_artifacts.publish_status_reason,
            "prior_publication_detected_flag": commercial_publish_artifacts.prior_publication_detected_flag,
            "noop_already_published_flag": commercial_publish_artifacts.noop_already_published_flag,
            "skipped_due_to_registry_duplicate_count": commercial_publish_artifacts.skipped_due_to_registry_duplicate_count,
            "skipped_due_to_review_count": commercial_publish_artifacts.skipped_due_to_review_count,
            "skipped_due_to_schema_count": commercial_publish_artifacts.skipped_due_to_schema_count,
            "skipped_due_to_mapping_count": commercial_publish_artifacts.skipped_due_to_mapping_count,
            "skipped_due_to_null_sku_count": commercial_publish_artifacts.skipped_due_to_null_sku_count,
            "skipped_duplicate_prediction_count": (
                commercial_publish_artifacts.skipped_duplicate_prediction_count
            ),
            "planning_horizon_days": 35,
            "allow_reprediction": False,
            "pilot_validation": {
                "pilot_validation_summary_csv_path": pilot_validation_artifacts.pilot_validation_summary_csv_path,
                "pilot_validation_summary_json_path": pilot_validation_artifacts.pilot_validation_summary_json_path,
                "pilot_validation_failures_csv_path": pilot_validation_artifacts.pilot_validation_failures_csv_path,
                "gold_standard_acceptance_results_csv_path": pilot_validation_artifacts.gold_standard_acceptance_results_csv_path,
                "gold_standard_acceptance_results_json_path": pilot_validation_artifacts.gold_standard_acceptance_results_json_path,
                "validation_manifest_path": pilot_validation_artifacts.validation_manifest_path,
                "pilot_validation_failure_count": pilot_validation_artifacts.validation_failure_count,
                "gold_standard_failure_count": pilot_validation_artifacts.gold_standard_failure_count,
                "validation_status": pilot_validation_artifacts.validation_status,
                "validation_status_reason": pilot_validation_artifacts.validation_status_reason,
                "validation_skipped_flag": pilot_validation_artifacts.validation_skipped_flag,
                "validation_skip_class": pilot_validation_artifacts.validation_skip_class,
                "validation_skip_message": pilot_validation_artifacts.validation_skip_message,
                "validation_skip_summary_path": pilot_validation_artifacts.validation_skip_summary_path,
                "validation_reference_cycle_path": pilot_validation_artifacts.validation_reference_cycle_path,
            },
            "publication_freshness_diagnostic_path": str(publication_freshness_diagnostic_new_path),
            "publication_freshness_diagnostic": publication_freshness_diagnostic_new.to_dict(),
            "commercial_outcome": commercial_outcome.to_dict(),
            "commercial_run_outcome_summary_path": str(commercial_run_outcome_summary_path),
            "commercial_delta_summary_path": str(commercial_delta_summary_path),
            "commercial_delta_summary": commercial_delta_summary.to_dict(),
            "commercial_delta_top_changes_csv_path": str(commercial_delta_top_changes_csv_path),
            "commercial_delta_store_summary_csv_path": str(commercial_delta_store_summary_csv_path),
            "commercial_change_explanations_csv_path": str(commercial_change_explanations_csv_path),
            "commercial_priority_queue_csv_path": str(commercial_priority_queue_csv_path),
            "commercial_action_summary_path": str(commercial_action_summary_path),
            "commercial_action_summary": commercial_action_summary.to_dict(),
            "commercial_outcome_attribution_csv_path": str(commercial_outcome_attribution_csv_path),
            "recommendation_effectiveness_summary_path": str(recommendation_effectiveness_summary_path),
            "recommendation_effectiveness_by_reason_csv_path": str(recommendation_effectiveness_by_reason_csv_path),
            "recommendation_learning_priority_queue_csv_path": str(recommendation_learning_priority_queue_csv_path),
            "recommendation_effectiveness_summary": recommendation_effectiveness_summary.to_dict(),
            "commercial_policy_calibration_summary_path": str(commercial_policy_calibration_summary_path),
            "commercial_policy_calibration_by_segment_csv_path": str(commercial_policy_calibration_by_segment_csv_path),
            "commercial_policy_watchlist_csv_path": str(commercial_policy_watchlist_csv_path),
            "commercial_policy_calibration_brief_path": str(commercial_policy_calibration_brief_path),
            "commercial_policy_calibration_summary": commercial_policy_calibration_summary.to_dict(),
            "commercial_policy_simulation_summary_path": str(commercial_policy_simulation_summary_path),
            "commercial_policy_simulation_by_segment_csv_path": str(commercial_policy_simulation_by_segment_csv_path),
            "commercial_policy_simulation_watchlist_csv_path": str(commercial_policy_simulation_watchlist_csv_path),
            "commercial_policy_simulation_brief_path": str(commercial_policy_simulation_brief_path),
            "commercial_action_instruction_summary_path": str(commercial_action_instruction_summary_path),
            "commercial_action_priority_queue_csv_path": str(commercial_action_priority_queue_csv_path),
            "commercial_action_by_segment_csv_path": str(commercial_action_by_segment_csv_path),
            "commercial_action_instruction_brief_path": str(commercial_action_instruction_brief_path),
            "commercial_action_instruction_readiness_class": commercial_action_instruction_summary.action_instruction_readiness_class,
            "commercial_action_instruction_readiness_reason": commercial_action_instruction_summary.action_instruction_readiness_reason,
            "commercial_top_model_owner_action_class": top_model_owner_action_class,
            "action_instruction_readiness_class": commercial_action_instruction_summary.action_instruction_readiness_class,
            "top_operator_action_class": commercial_action_instruction_summary.top_operator_action_class,
            "top_model_owner_action_class": commercial_action_instruction_summary.top_model_owner_action_class,
            "operator_attention_class": commercial_action_instruction_summary.operator_attention_class,
            "action_pack_materiality_class": commercial_action_instruction_summary.action_pack_materiality_class,
            "commercial_action_instruction": commercial_action_instruction_summary.to_dict(),
            "commercial_policy_simulation_summary": commercial_policy_simulation_summary.to_dict(),
        }
        manifest_payload["audit"] = {
            "manifest_path": audit_artifacts.audit_manifest_path,
            "summary_json_path": audit_artifacts.summary_json_path,
            "summary_csv_path": audit_artifacts.summary_csv_path,
            "report_paths": audit_artifacts.report_paths,
        }
        manifest_payload["local_inspection"] = (
            local_inspection_artifacts.to_dict() if local_inspection_artifacts is not None else None
        )
        manifest_payload["operator_progress"] = {
            "log_path": str(settings.artifacts.operator_log_path(run_id)),
            "summary_path": str(settings.artifacts.operator_summary_path(run_id)),
            "summary_csv_path": str(settings.artifacts.operator_summary_csv_path(run_id)),
            "stage_timings_path": str(settings.artifacts.operator_stage_timings_path(run_id)),
        }
        manifest_payload["final_outputs"] = {
            "operator_summary_json_path": str(settings.artifacts.operator_summary_path(run_id)),
            "operator_summary_csv_path": str(settings.artifacts.operator_summary_csv_path(run_id)),
            "store_prediction_download_path": store_prediction_artifacts.csv_path,
            "nas_store_prediction_download_path": store_prediction_artifacts.csv_path,
            "store_prediction_user_csv_paths": json.dumps(
                list(store_prediction_artifacts.per_store_promotion_csv_paths)
            ),
            "store_prediction_manifest_csv_path": store_prediction_artifacts.manifest_csv_path,
            "store_prediction_manifest_json_path": store_prediction_artifacts.manifest_path,
            "store_prediction_per_store_csv_paths": json.dumps(
                list(store_prediction_artifacts.per_store_csv_paths)
            ),
            "store_prediction_per_store_promotion_csv_paths": json.dumps(
                list(store_prediction_artifacts.per_store_promotion_csv_paths)
            ),
            "commercial_prediction_registry_path": (
                commercial_publish_artifacts.prediction_registry_path
            ),
            "commercial_store_cycle_manifest_paths": json.dumps(
                list(commercial_publish_artifacts.store_cycle_manifest_paths)
            ),
            "commercial_pos_upload_paths": json.dumps(
                list(commercial_publish_artifacts.pos_upload_paths)
            ),
            "commercial_review_paths": json.dumps(
                list(commercial_publish_artifacts.review_paths)
            ),
            "commercial_summary_paths": json.dumps(
                list(commercial_publish_artifacts.summary_paths)
            ),
            "commercial_reconciliation_paths": json.dumps(
                list(commercial_publish_artifacts.reconciliation_paths)
            ),
            "commercial_publication_summary_path": commercial_publish_artifacts.publication_summary_path,
            "commercial_publish_status": commercial_publish_artifacts.publish_status,
            "commercial_publish_status_reason": commercial_publish_artifacts.publish_status_reason,
            "commercial_pos_upload_row_count": commercial_publish_artifacts.pos_upload_row_count,
            "commercial_pos_excluded_row_count": commercial_publish_artifacts.pos_excluded_row_count,
            "commercial_publishability_split_path": str(commercial_publishability_split_path),
            **split_to_manifest_payload(commercial_publishability_split),
            "commercial_prior_publication_detected_flag": commercial_publish_artifacts.prior_publication_detected_flag,
            "commercial_duplicate_registry_skip_count": commercial_publish_artifacts.skipped_due_to_registry_duplicate_count,
            "commercial_noop_already_published_flag": commercial_publish_artifacts.noop_already_published_flag,
            "commercial_outcome_class": commercial_outcome.commercial_outcome_class,
            "commercial_outcome_reason": commercial_outcome.commercial_outcome_reason,
            "commercial_outcome_message": commercial_outcome.commercial_outcome_message,
            "commercial_new_publication_count": commercial_outcome.commercial_new_publication_count,
            "commercial_noop_flag": commercial_outcome.commercial_noop_flag,
            "commercial_failure_flag": commercial_outcome.commercial_failure_flag,
            "commercial_run_outcome_summary_path": str(commercial_run_outcome_summary_path),
            "publication_freshness_diagnostic_path": str(publication_freshness_diagnostic_new_path),
            "commercial_freshness_class": commercial_freshness.freshness_class,
            "commercial_freshness_reason": commercial_freshness.freshness_reason,
            "commercial_new_value_created_flag": commercial_freshness.commercially_new_value_created_flag,
            "commercial_replay_safety_class": commercial_replay_safety.replay_safety_class,
            "commercial_replay_safety_reason": commercial_replay_safety.replay_safety_reason,
            "commercial_replay_safe_without_input_change_flag": commercial_replay_safety.safe_to_rerun_without_input_change_flag,
            "commercial_replay_safety_summary_path": str(commercial_replay_safety_summary_path),
            "commercial_delta_class": commercial_delta_summary.delta_class,
            "commercial_delta_reason": commercial_delta_summary.delta_reason,
            "commercial_materiality_class": commercial_delta_summary.materiality_class,
            "commercial_materiality_reason": commercial_delta_summary.materiality_reason,
            "commercial_materially_changed_flag": commercial_delta_summary.materially_changed_flag,
            "commercial_operator_attention_recommended_flag": commercial_delta_summary.operator_attention_recommended_flag,
            "comparable_prior_cycle_found_flag": commercial_delta_summary.comparable_prior_cycle_found_flag,
            "comparable_prior_cycle_run_id": (
                commercial_delta_summary.prior_cycle_run_id
                if commercial_delta_summary.prior_cycle_run_id is not None
                else "unavailable"
            ),
            "commercial_delta_summary_path": str(commercial_delta_summary_path),
            "commercial_delta_top_changes_csv_path": str(commercial_delta_top_changes_csv_path),
            "commercial_delta_store_summary_csv_path": str(commercial_delta_store_summary_csv_path),
            "commercial_change_explanations_csv_path": str(commercial_change_explanations_csv_path),
            "commercial_priority_queue_csv_path": str(commercial_priority_queue_csv_path),
            "commercial_action_summary_path": str(commercial_action_summary_path),
            "commercial_top_operator_action_class": top_operator_action_class,
            "commercial_top_operator_priority_band": top_operator_priority_band,
            "commercial_review_now_count": commercial_action_summary.action_review_now_count,
            "commercial_publish_now_count": commercial_action_summary.action_publish_now_count,
            "commercial_defect_action_count": commercial_action_summary.action_investigate_defect_count,
            "commercial_outcome_attribution_csv_path": str(commercial_outcome_attribution_csv_path),
            "recommendation_effectiveness_summary_path": str(recommendation_effectiveness_summary_path),
            "recommendation_effectiveness_by_reason_csv_path": str(recommendation_effectiveness_by_reason_csv_path),
            "recommendation_learning_priority_queue_csv_path": str(recommendation_learning_priority_queue_csv_path),
            "attribution_ready_count": recommendation_effectiveness_summary.attribution_ready_count,
            "attribution_effective_count": recommendation_effectiveness_summary.attribution_effective_count,
            "attribution_harmful_count": recommendation_effectiveness_summary.attribution_harmful_count,
            "attribution_inconclusive_count": recommendation_effectiveness_summary.attribution_inconclusive_count,
            "commercial_learning_signal_strength_class": recommendation_effectiveness_summary.commercial_learning_signal_strength_class,
            "commercial_policy_calibration_summary_path": str(commercial_policy_calibration_summary_path),
            "commercial_policy_calibration_by_segment_csv_path": str(commercial_policy_calibration_by_segment_csv_path),
            "commercial_policy_watchlist_csv_path": str(commercial_policy_watchlist_csv_path),
            "commercial_policy_calibration_brief_path": str(commercial_policy_calibration_brief_path),
            "policy_signal_class": commercial_policy_calibration_summary.policy_signal_class,
            "calibration_readiness_class": commercial_policy_calibration_summary.calibration_readiness_class,
            "threshold_direction_class": commercial_policy_calibration_summary.threshold_direction_class,
            "commercial_policy_confidence_class": commercial_policy_calibration_summary.confidence_class,
            "commercial_policy_simulation_summary_path": str(commercial_policy_simulation_summary_path),
            "commercial_policy_simulation_by_segment_csv_path": str(commercial_policy_simulation_by_segment_csv_path),
            "commercial_policy_simulation_watchlist_csv_path": str(commercial_policy_simulation_watchlist_csv_path),
            "commercial_policy_simulation_brief_path": str(commercial_policy_simulation_brief_path),
            "commercial_action_instruction_summary_path": str(commercial_action_instruction_summary_path),
            "commercial_action_priority_queue_csv_path": str(commercial_action_priority_queue_csv_path),
            "commercial_action_by_segment_csv_path": str(commercial_action_by_segment_csv_path),
            "commercial_action_instruction_brief_path": str(commercial_action_instruction_brief_path),
            "commercial_action_instruction_readiness_class": commercial_action_instruction_summary.action_instruction_readiness_class,
            "commercial_action_instruction_readiness_reason": commercial_action_instruction_summary.action_instruction_readiness_reason,
            "commercial_top_model_owner_action_class": top_model_owner_action_class,
            "action_instruction_readiness_class": commercial_action_instruction_summary.action_instruction_readiness_class,
            "top_operator_action_class": commercial_action_instruction_summary.top_operator_action_class,
            "top_model_owner_action_class": commercial_action_instruction_summary.top_model_owner_action_class,
            "operator_attention_class": commercial_action_instruction_summary.operator_attention_class,
            "action_pack_materiality_class": commercial_action_instruction_summary.action_pack_materiality_class,
            "commercial_action_instruction": commercial_action_instruction_summary.to_dict(),
            "simulation_readiness_class": commercial_policy_simulation_summary.simulation_readiness_class,
            "simulated_policy_direction_class": commercial_policy_simulation_summary.simulated_policy_direction_class,
            "simulated_materiality_class": (
                commercial_policy_simulation_summary.simulated_materiality_class
                if commercial_policy_simulation_summary.simulated_materiality_class is not None
                else "not_ready"
            ),
            "simulated_risk_class": (
                commercial_policy_simulation_summary.simulated_risk_class
                if commercial_policy_simulation_summary.simulated_risk_class is not None
                else "not_ready"
            ),
            "simulation_operator_review_recommended_flag": commercial_policy_simulation_summary.operator_review_recommended_flag,
            "simulation_model_owner_review_recommended_flag": commercial_policy_simulation_summary.model_owner_review_recommended_flag,
            "simulation_net_publish_delta": commercial_policy_simulation_summary.net_publish_delta,
            "simulation_affected_row_count": commercial_policy_simulation_summary.affected_row_count,
            "commercial_diagnostics_paths": json.dumps(
                list(commercial_publish_artifacts.diagnostics_paths)
            ),
            "commercial_skipped_paths": json.dumps(
                list(commercial_publish_artifacts.skipped_paths)
            ),
            "pilot_validation_summary_csv_path": pilot_validation_artifacts.pilot_validation_summary_csv_path,
            "pilot_validation_summary_json_path": pilot_validation_artifacts.pilot_validation_summary_json_path,
            "pilot_validation_failures_csv_path": pilot_validation_artifacts.pilot_validation_failures_csv_path,
            "gold_standard_acceptance_results_csv_path": pilot_validation_artifacts.gold_standard_acceptance_results_csv_path,
            "gold_standard_acceptance_results_json_path": pilot_validation_artifacts.gold_standard_acceptance_results_json_path,
            "validation_manifest_path": pilot_validation_artifacts.validation_manifest_path,
            "validation_status": pilot_validation_artifacts.validation_status,
            "validation_status_reason": pilot_validation_artifacts.validation_status_reason,
            "validation_skipped_flag": str(pilot_validation_artifacts.validation_skipped_flag).lower(),
            "validation_skip_class": pilot_validation_artifacts.validation_skip_class,
            "validation_skip_message": pilot_validation_artifacts.validation_skip_message,
            "validation_skip_summary_path": pilot_validation_artifacts.validation_skip_summary_path,
            "validation_reference_cycle_path": pilot_validation_artifacts.validation_reference_cycle_path,
            "decision_surface_csv_path": decision_surface_csv_path,
            "inspection_review_packet_csv_path": inspection_review_packet_csv_path,
            "local_inspection_csv_path": (
                local_inspection_artifacts.store_prediction_csv_path
                if local_inspection_artifacts is not None
                else "disabled"
            ),
            "local_decision_surface_csv_path": (
                local_inspection_artifacts.decision_surface_csv_path
                if local_inspection_artifacts is not None
                else "disabled"
            ),
            "local_review_packet_csv_path": (
                local_inspection_artifacts.review_packet_csv_path
                if local_inspection_artifacts is not None
                else "disabled"
            ),
            "local_run_summary_path": (
                local_inspection_artifacts.run_summary_path
                if local_inspection_artifacts is not None
                else "disabled"
            ),
            "operator_review_packet_csv_path": inspection_review_packet_csv_path,
            "decision_surface_review_packet_path": inspection_review_packet_csv_path,
            "decision_surface_inspection_manifest_path": decision_surface_artifacts.inspection_manifest_path,
            "completed_preflight_summary_path": (
                completed_extraction.preflight_summary_json_path
                or completed_extraction.partition_summary_path
            ),
            "completed_rendered_preflight_sql_path": completed_extraction.rendered_preflight_sql_path,
            "completed_rendered_preflight_sql_parameters_path": (
                completed_extraction.rendered_preflight_sql_parameters_path
            ),
            "completed_rendered_sql_path": completed_extraction.rendered_sql_path,
            "completed_rendered_sql_parameters_path": completed_extraction.rendered_sql_parameters_path,
            "completed_extraction_telemetry_json_path": completed_extraction.telemetry_json_path,
            "completed_extraction_telemetry_csv_path": completed_extraction.telemetry_csv_path,
            "completed_partition_summary_path": completed_extraction.partition_summary_path,
            "completed_partition_retries_json_path": completed_partition_retries_json_path,
            "completed_partition_retries_csv_path": completed_partition_retries_csv_path,
            "completed_preflight_cost_diagnostic_path": completed_extraction.completed_preflight_cost_diagnostic_path,
            "completed_preflight_model_learning_diagnostic_path": completed_extraction.completed_preflight_model_learning_diagnostic_path,
            "completed_proof_fallback_used": str(completed_extraction.completed_proof_fallback_used).lower(),
            "completed_proof_fallback_mode": completed_extraction.completed_proof_fallback_mode or "none",
            "completed_proof_fallback_reason": completed_extraction.completed_proof_fallback_reason or "none",
            "completed_sql_diagnostics_summary_path": (
                completed_extraction.diagnostics_summary_json_path
                or completed_extraction.partition_summary_path
            ),
            "future_rendered_sql_path": future_extraction.rendered_sql_path,
            "future_rendered_sql_parameters_path": future_extraction.rendered_sql_parameters_path,
            "future_extraction_telemetry_json_path": future_extraction.telemetry_json_path,
            "future_extraction_telemetry_csv_path": future_extraction.telemetry_csv_path,
            "future_sql_diagnostics_summary_path": (
                future_extraction.diagnostics_summary_json_path
                or future_extraction.partition_summary_path
            ),
            **_stage6_success_final_output_fields(
                stage6_plan=stage6_plan,
                stage6_guardrail_path=stage6_guardrail_path,
                stage6_plan_path=stage6_plan_path,
                stage6_failure_summary_path=stage6_failure_summary_path,
            ),
            "audit_summary_json_path": audit_artifacts.summary_json_path,
            "audit_summary_csv_path": audit_artifacts.summary_csv_path,
            "audit_manifest_path": audit_artifacts.audit_manifest_path,
            "operator_log_path": str(settings.artifacts.operator_log_path(run_id)),
            "operational_cycle_manifest_path": str(manifest_path),
        }
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
        progress.complete_stage(
            file_count=9 if local_inspection_artifacts is not None else 6,
            output_paths=(
                manifest_path,
                *( 
                    (local_inspection_artifacts.store_prediction_csv_path,)
                    if local_inspection_artifacts is not None
                    else ()
                ),
                *( 
                    (local_inspection_artifacts.run_summary_path,)
                    if local_inspection_artifacts is not None
                    else ()
                ),
                settings.artifacts.operator_log_path(run_id),
                settings.artifacts.operator_summary_path(run_id),
                settings.artifacts.operator_summary_csv_path(run_id),
                settings.artifacts.operator_stage_timings_path(run_id),
            ),
            note="Top-level manifest, local inspection copies, and operator trace targets prepared.",
        )
        progress.emit_final_outputs(
            outputs={
                "operational_cycle_manifest_path": str(manifest_path),
                "operator_log_path": str(settings.artifacts.operator_log_path(run_id)),
                "operator_summary_json_path": str(settings.artifacts.operator_summary_path(run_id)),
                "operator_summary_csv_path": str(settings.artifacts.operator_summary_csv_path(run_id)),
                "completed_partition_retries_json_path": completed_partition_retries_json_path,
                "completed_partition_retries_csv_path": completed_partition_retries_csv_path,
                "completed_preflight_cost_diagnostic_path": completed_extraction.completed_preflight_cost_diagnostic_path,
                "completed_preflight_model_learning_diagnostic_path": completed_extraction.completed_preflight_model_learning_diagnostic_path,
                "completed_proof_fallback_used": str(completed_extraction.completed_proof_fallback_used).lower(),
                "completed_proof_fallback_mode": completed_extraction.completed_proof_fallback_mode or "none",
                "completed_proof_fallback_reason": completed_extraction.completed_proof_fallback_reason or "none",
                "store_prediction_csv_path": store_prediction_artifacts.csv_path,
                "nas_store_prediction_download_path": store_prediction_artifacts.csv_path,
                "store_prediction_download_path": store_prediction_artifacts.csv_path,
                "store_prediction_user_csv_paths": json.dumps(
                    list(store_prediction_artifacts.per_store_promotion_csv_paths)
                ),
                "commercial_prediction_registry_path": (
                    commercial_publish_artifacts.prediction_registry_path
                ),
                "commercial_store_cycle_manifest_paths": json.dumps(
                    list(commercial_publish_artifacts.store_cycle_manifest_paths)
                ),
                "commercial_pos_upload_paths": json.dumps(
                    list(commercial_publish_artifacts.pos_upload_paths)
                ),
                "commercial_reconciliation_paths": json.dumps(
                    list(commercial_publish_artifacts.reconciliation_paths)
                ),
                "commercial_publication_summary_path": commercial_publish_artifacts.publication_summary_path,
                "commercial_publish_status": commercial_publish_artifacts.publish_status,
                "commercial_publish_status_reason": commercial_publish_artifacts.publish_status_reason,
                "commercial_pos_upload_row_count": commercial_publish_artifacts.pos_upload_row_count,
                "commercial_pos_excluded_row_count": commercial_publish_artifacts.pos_excluded_row_count,
                "commercial_publishability_split_path": str(commercial_publishability_split_path),
                **split_to_manifest_payload(commercial_publishability_split),
                "commercial_prior_publication_detected_flag": commercial_publish_artifacts.prior_publication_detected_flag,
                "commercial_duplicate_registry_skip_count": commercial_publish_artifacts.skipped_due_to_registry_duplicate_count,
                "commercial_noop_already_published_flag": commercial_publish_artifacts.noop_already_published_flag,
                "commercial_outcome_class": commercial_outcome.commercial_outcome_class,
                "commercial_outcome_reason": commercial_outcome.commercial_outcome_reason,
                "commercial_outcome_message": commercial_outcome.commercial_outcome_message,
                "commercial_new_publication_count": commercial_outcome.commercial_new_publication_count,
                "commercial_noop_flag": str(commercial_outcome.commercial_noop_flag).lower(),
                "commercial_failure_flag": str(commercial_outcome.commercial_failure_flag).lower(),
                "commercial_run_outcome_summary_path": str(commercial_run_outcome_summary_path),
                "publication_freshness_diagnostic_path": str(publication_freshness_diagnostic_new_path),
                "commercial_freshness_class": commercial_freshness.freshness_class,
                "commercial_freshness_reason": commercial_freshness.freshness_reason,
                "commercial_new_value_created_flag": commercial_freshness.commercially_new_value_created_flag,
                "commercial_replay_safety_class": commercial_replay_safety.replay_safety_class,
                "commercial_replay_safety_reason": commercial_replay_safety.replay_safety_reason,
                "commercial_replay_safe_without_input_change_flag": commercial_replay_safety.safe_to_rerun_without_input_change_flag,
                "commercial_replay_safety_summary_path": str(commercial_replay_safety_summary_path),
                "commercial_delta_class": commercial_delta_summary.delta_class,
                "commercial_delta_reason": commercial_delta_summary.delta_reason,
                "commercial_materiality_class": commercial_delta_summary.materiality_class,
                "commercial_materiality_reason": commercial_delta_summary.materiality_reason,
                "commercial_materially_changed_flag": commercial_delta_summary.materially_changed_flag,
                "commercial_operator_attention_recommended_flag": commercial_delta_summary.operator_attention_recommended_flag,
                "comparable_prior_cycle_found_flag": str(
                    commercial_delta_summary.comparable_prior_cycle_found_flag
                ).lower(),
                "comparable_prior_cycle_run_id": (
                    commercial_delta_summary.prior_cycle_run_id
                    if commercial_delta_summary.prior_cycle_run_id is not None
                    else "unavailable"
                ),
                "commercial_delta_summary_path": str(commercial_delta_summary_path),
                "commercial_delta_top_changes_csv_path": str(commercial_delta_top_changes_csv_path),
                "commercial_delta_store_summary_csv_path": str(commercial_delta_store_summary_csv_path),
                "commercial_change_explanations_csv_path": str(commercial_change_explanations_csv_path),
                "commercial_priority_queue_csv_path": str(commercial_priority_queue_csv_path),
                "commercial_action_summary_path": str(commercial_action_summary_path),
                "commercial_top_operator_action_class": top_operator_action_class,
                "commercial_top_operator_priority_band": top_operator_priority_band,
                "commercial_review_now_count": commercial_action_summary.action_review_now_count,
                "commercial_publish_now_count": commercial_action_summary.action_publish_now_count,
                "commercial_defect_action_count": commercial_action_summary.action_investigate_defect_count,
                "commercial_outcome_attribution_csv_path": str(commercial_outcome_attribution_csv_path),
                "recommendation_effectiveness_summary_path": str(recommendation_effectiveness_summary_path),
                "recommendation_effectiveness_by_reason_csv_path": str(recommendation_effectiveness_by_reason_csv_path),
                "recommendation_learning_priority_queue_csv_path": str(recommendation_learning_priority_queue_csv_path),
                "attribution_ready_count": recommendation_effectiveness_summary.attribution_ready_count,
                "attribution_effective_count": recommendation_effectiveness_summary.attribution_effective_count,
                "attribution_harmful_count": recommendation_effectiveness_summary.attribution_harmful_count,
                "attribution_inconclusive_count": recommendation_effectiveness_summary.attribution_inconclusive_count,
                "commercial_learning_signal_strength_class": recommendation_effectiveness_summary.commercial_learning_signal_strength_class,
                "commercial_policy_calibration_summary_path": str(commercial_policy_calibration_summary_path),
                "commercial_policy_calibration_by_segment_csv_path": str(commercial_policy_calibration_by_segment_csv_path),
                "commercial_policy_watchlist_csv_path": str(commercial_policy_watchlist_csv_path),
                "commercial_policy_calibration_brief_path": str(commercial_policy_calibration_brief_path),
                "policy_signal_class": commercial_policy_calibration_summary.policy_signal_class,
                "calibration_readiness_class": commercial_policy_calibration_summary.calibration_readiness_class,
                "threshold_direction_class": commercial_policy_calibration_summary.threshold_direction_class,
                "commercial_policy_confidence_class": commercial_policy_calibration_summary.confidence_class,
                "commercial_policy_simulation_summary_path": str(commercial_policy_simulation_summary_path),
                "commercial_policy_simulation_by_segment_csv_path": str(commercial_policy_simulation_by_segment_csv_path),
                "commercial_policy_simulation_watchlist_csv_path": str(commercial_policy_simulation_watchlist_csv_path),
                "commercial_policy_simulation_brief_path": str(commercial_policy_simulation_brief_path),
                "simulation_readiness_class": commercial_policy_simulation_summary.simulation_readiness_class,
                "simulated_policy_direction_class": commercial_policy_simulation_summary.simulated_policy_direction_class,
                "simulated_materiality_class": (
                    commercial_policy_simulation_summary.simulated_materiality_class
                    if commercial_policy_simulation_summary.simulated_materiality_class is not None
                    else "not_ready"
                ),
                "simulated_risk_class": (
                    commercial_policy_simulation_summary.simulated_risk_class
                    if commercial_policy_simulation_summary.simulated_risk_class is not None
                    else "not_ready"
                ),
                "simulation_operator_review_recommended_flag": str(
                    commercial_policy_simulation_summary.operator_review_recommended_flag
                ).lower(),
                "simulation_model_owner_review_recommended_flag": str(
                    commercial_policy_simulation_summary.model_owner_review_recommended_flag
                ).lower(),
                "simulation_net_publish_delta": commercial_policy_simulation_summary.net_publish_delta,
                "simulation_affected_row_count": commercial_policy_simulation_summary.affected_row_count,
                "commercial_diagnostics_paths": json.dumps(
                    list(commercial_publish_artifacts.diagnostics_paths)
                ),
                "commercial_skipped_paths": json.dumps(
                    list(commercial_publish_artifacts.skipped_paths)
                ),
                "pilot_validation_summary_csv_path": pilot_validation_artifacts.pilot_validation_summary_csv_path,
                "pilot_validation_failures_csv_path": pilot_validation_artifacts.pilot_validation_failures_csv_path,
                "gold_standard_acceptance_results_csv_path": pilot_validation_artifacts.gold_standard_acceptance_results_csv_path,
                "validation_manifest_path": pilot_validation_artifacts.validation_manifest_path,
                "validation_status": pilot_validation_artifacts.validation_status,
                "validation_status_reason": pilot_validation_artifacts.validation_status_reason,
                "validation_skipped_flag": str(pilot_validation_artifacts.validation_skipped_flag).lower(),
                "validation_skip_class": pilot_validation_artifacts.validation_skip_class,
                "validation_skip_message": pilot_validation_artifacts.validation_skip_message,
                "validation_skip_summary_path": pilot_validation_artifacts.validation_skip_summary_path,
                "validation_reference_cycle_path": pilot_validation_artifacts.validation_reference_cycle_path,
                "decision_surface_csv_path": decision_surface_csv_path,
                "local_inspection_csv_path": (
                    local_inspection_artifacts.store_prediction_csv_path
                    if local_inspection_artifacts is not None
                    else "disabled"
                ),
                "inspection_review_packet_csv_path": inspection_review_packet_csv_path,
                "completed_preflight_summary_path": (
                    completed_extraction.preflight_summary_json_path
                    or completed_extraction.partition_summary_path
                    or "disabled"
                ),
                "completed_rendered_sql_path": completed_extraction.rendered_sql_path or "unavailable",
                "completed_extraction_telemetry_json_path": completed_extraction.telemetry_json_path or "unavailable",
                "completed_extraction_telemetry_csv_path": completed_extraction.telemetry_csv_path or "unavailable",
                "completed_partition_summary_path": completed_extraction.partition_summary_path or "disabled",
                "future_rendered_sql_path": future_extraction.rendered_sql_path or "unavailable",
                "future_extraction_telemetry_json_path": future_extraction.telemetry_json_path or "unavailable",
                "future_extraction_telemetry_csv_path": future_extraction.telemetry_csv_path or "unavailable",
                "completed_sql_diagnostics_summary_path": (
                    completed_extraction.diagnostics_summary_json_path
                    or completed_extraction.partition_summary_path
                    or "unavailable"
                ),
                "future_sql_diagnostics_summary_path": (
                    future_extraction.diagnostics_summary_json_path
                    or future_extraction.partition_summary_path
                    or "unavailable"
                ),
                **_stage6_success_final_output_fields(
                    stage6_plan=stage6_plan,
                    stage6_guardrail_path=stage6_guardrail_path,
                    stage6_plan_path=stage6_plan_path,
                    stage6_failure_summary_path=stage6_failure_summary_path,
                ),
                "audit_summary_json_path": audit_artifacts.summary_json_path,
                "audit_summary_csv_path": audit_artifacts.summary_csv_path,
                "publication_opportunity_class": publication_opportunity.publication_opportunity_class,
                "publication_opportunity_reason": publication_opportunity.publication_opportunity_reason,
                "publication_opportunity_message": publication_opportunity.publication_opportunity_message,
                "publish_reconciliation_summary_path": (
                    str(publish_reconciliation_summary_path)
                    if publish_reconciliation_summary is not None
                    else "unavailable"
                ),
                "commercial_stage_timing_summary_path": str(
                    commercial_stage_timing_summary_path
                ),
                "duplicate_registry_skip_summary_path": (
                    str(duplicate_registry_skip_summary_path)
                    if duplicate_registry_skip_summary_path is not None
                    else "unavailable"
                ),
                "commercial_operator_brief_path": str(commercial_operator_brief_path),
                "action_instruction_readiness_class": commercial_action_instruction_summary.action_instruction_readiness_class,
                "top_operator_action_class": commercial_action_instruction_summary.top_operator_action_class,
                "top_model_owner_action_class": commercial_action_instruction_summary.top_model_owner_action_class,
                "operator_attention_class": commercial_action_instruction_summary.operator_attention_class,
                "action_pack_materiality_class": commercial_action_instruction_summary.action_pack_materiality_class,
            }
        )
        operator_artifacts = progress.persist(
            status="completed",
            final_outputs=manifest_payload["final_outputs"],
        )
        if local_inspection_artifacts is not None:
            local_inspection_artifacts = write_local_inspection_outputs(
                run_id=run_id,
                as_of_date=settings.as_of_date.isoformat(),
                execution_mode=execution_mode,
                artifact_paths=settings.artifacts,
                nas_store_prediction_csv_path=store_prediction_artifacts.csv_path,
                nas_decision_surface_csv_path=decision_surface_csv_path,
                nas_review_packet_csv_path=inspection_review_packet_csv_path,
                operational_cycle_manifest_path=str(manifest_path),
                operator_log_path=operator_artifacts.log_path,
                audit_summary_json_path=audit_artifacts.summary_json_path,
                audit_summary_csv_path=audit_artifacts.summary_csv_path,
                operator_summary_json_path=operator_artifacts.summary_path,
                operator_summary_csv_path=operator_artifacts.summary_csv_path,
            )
        manifest_payload["operator_progress"] = operator_artifacts.to_dict()
        manifest_payload["local_inspection"] = (
            local_inspection_artifacts.to_dict() if local_inspection_artifacts is not None else None
        )
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")

        return PromotionOperationalCycleArtifacts(
            manifest_path=str(manifest_path),
            nas_bootstrap_summary_path=nas_bootstrap_artifacts.summary_path,
            nas_root=str(settings.artifacts.root),
            local_inspection_root=(
                str(settings.artifacts.local_inspection_root)
                if settings.artifacts.local_inspection_root is not None
                else None
            ),
            completed_base_path=completed_extraction.base_path,
            completed_base_manifest_path=completed_extraction.manifest_path,
            completed_partition_summary_path=completed_extraction.partition_summary_path,
            future_base_path=future_extraction.base_path,
            future_base_manifest_path=future_extraction.manifest_path,
            dataset_path=dataset.dataset_path,
            dataset_manifest_path=dataset.manifest_path,
            model_manifest_path=training_artifacts.manifest_path,
            scoring_manifest_path=scoring_artifacts.manifest_path,
            score_report_manifest_path=reporting_artifacts.report_paths["report_manifest"],
            decision_surface_manifest_path=decision_surface_artifacts.decision_surface_manifest_path,
            decision_surface_execution_summary_path=decision_surface_artifacts.execution_summary_path,
            decision_surface_inspection_manifest_path=decision_surface_artifacts.inspection_manifest_path,
            inspection_review_packet_csv_path=inspection_review_packet_csv_path,
            store_prediction_master_csv_path=store_prediction_artifacts.master_csv_path,
            store_prediction_download_path=store_prediction_artifacts.csv_path,
            store_prediction_per_store_csv_paths=store_prediction_artifacts.per_store_csv_paths,
            store_prediction_per_store_promotion_csv_paths=(
                store_prediction_artifacts.per_store_promotion_csv_paths
            ),
            store_prediction_reconciliation_csv_path=store_prediction_artifacts.reconciliation_csv_path,
            store_prediction_manifest_path=store_prediction_artifacts.manifest_path,
            store_prediction_manifest_csv_path=store_prediction_artifacts.manifest_csv_path,
            commercial_prediction_registry_path=(
                commercial_publish_artifacts.prediction_registry_path
            ),
            commercial_prediction_manifest_paths=(
                commercial_publish_artifacts.store_cycle_manifest_paths
            ),
            commercial_pos_upload_paths=commercial_publish_artifacts.pos_upload_paths,
            commercial_review_paths=commercial_publish_artifacts.review_paths,
            commercial_summary_paths=commercial_publish_artifacts.summary_paths,
            commercial_reconciliation_paths=commercial_publish_artifacts.reconciliation_paths,
            commercial_publication_summary_path=commercial_publish_artifacts.publication_summary_path,
            commercial_diagnostics_paths=commercial_publish_artifacts.diagnostics_paths,
            commercial_skipped_paths=commercial_publish_artifacts.skipped_paths,
            pilot_validation_summary_csv_path=pilot_validation_artifacts.pilot_validation_summary_csv_path,
            pilot_validation_summary_json_path=pilot_validation_artifacts.pilot_validation_summary_json_path,
            pilot_validation_failures_csv_path=pilot_validation_artifacts.pilot_validation_failures_csv_path,
            gold_standard_acceptance_results_csv_path=pilot_validation_artifacts.gold_standard_acceptance_results_csv_path,
            gold_standard_acceptance_results_json_path=pilot_validation_artifacts.gold_standard_acceptance_results_json_path,
            validation_manifest_path=pilot_validation_artifacts.validation_manifest_path,
            validation_skip_summary_path=pilot_validation_artifacts.validation_skip_summary_path,
            commercial_run_outcome_summary_path=str(commercial_run_outcome_summary_path),
            publication_freshness_diagnostic_path=str(publication_freshness_diagnostic_new_path),
            commercial_delta_summary_path=str(commercial_delta_summary_path),
            commercial_delta_top_changes_csv_path=str(commercial_delta_top_changes_csv_path),
            commercial_delta_store_summary_csv_path=str(commercial_delta_store_summary_csv_path),
            commercial_change_explanations_csv_path=str(commercial_change_explanations_csv_path),
            commercial_priority_queue_csv_path=str(commercial_priority_queue_csv_path),
            commercial_action_summary_path=str(commercial_action_summary_path),
            commercial_outcome_attribution_csv_path=str(commercial_outcome_attribution_csv_path),
            recommendation_effectiveness_summary_path=str(recommendation_effectiveness_summary_path),
            recommendation_effectiveness_by_reason_csv_path=str(recommendation_effectiveness_by_reason_csv_path),
            recommendation_learning_priority_queue_csv_path=str(recommendation_learning_priority_queue_csv_path),
            commercial_policy_calibration_summary_path=str(commercial_policy_calibration_summary_path),
            commercial_policy_calibration_by_segment_csv_path=str(commercial_policy_calibration_by_segment_csv_path),
            commercial_policy_watchlist_csv_path=str(commercial_policy_watchlist_csv_path),
            commercial_policy_calibration_brief_path=str(commercial_policy_calibration_brief_path),
            commercial_policy_simulation_summary_path=str(commercial_policy_simulation_summary_path),
            commercial_policy_simulation_by_segment_csv_path=str(commercial_policy_simulation_by_segment_csv_path),
            commercial_policy_simulation_watchlist_csv_path=str(commercial_policy_simulation_watchlist_csv_path),
            commercial_policy_simulation_brief_path=str(commercial_policy_simulation_brief_path),
            commercial_action_instruction_summary_path=str(commercial_action_instruction_summary_path),
            commercial_action_priority_queue_csv_path=str(commercial_action_priority_queue_csv_path),
            commercial_action_by_segment_csv_path=str(commercial_action_by_segment_csv_path),
            commercial_action_instruction_brief_path=str(commercial_action_instruction_brief_path),
            local_store_prediction_download_path=(
                local_inspection_artifacts.store_prediction_csv_path
                if local_inspection_artifacts is not None
                else None
            ),
            local_decision_surface_csv_path=(
                local_inspection_artifacts.decision_surface_csv_path
                if local_inspection_artifacts is not None
                else None
            ),
            local_review_packet_csv_path=(
                local_inspection_artifacts.review_packet_csv_path
                if local_inspection_artifacts is not None
                else None
            ),
            local_run_summary_path=(
                local_inspection_artifacts.run_summary_path
                if local_inspection_artifacts is not None
                else None
            ),
            audit_manifest_path=audit_artifacts.audit_manifest_path,
            audit_summary_json_path=audit_artifacts.summary_json_path,
            audit_summary_csv_path=audit_artifacts.summary_csv_path,
            operator_log_path=operator_artifacts.log_path,
            operator_summary_path=operator_artifacts.summary_path,
            operator_summary_csv_path=operator_artifacts.summary_csv_path,
            operator_stage_timings_path=operator_artifacts.stage_timings_path,
            promotion_demand_backtest_csv_path=backtest_paths.rows_csv_path,
            promotion_demand_backtest_parquet_path=backtest_paths.rows_parquet_path,
            promotion_demand_backtest_summary_path=backtest_paths.summary_json_path,
            promotion_demand_backtest_by_segment_csv_path=backtest_paths.by_segment_csv_path,
            promotion_demand_backtest_watchlist_csv_path=backtest_paths.watchlist_csv_path,
            promotion_demand_backtest_brief_path=backtest_paths.brief_md_path,
            promotion_demand_backtest_manifest_path=backtest_paths.manifest_json_path,
            promotion_demand_backtest_calibration_summary_path=backtest_paths.calibration_summary_json_path,
            promotion_demand_backtest_calibration_brief_path=backtest_paths.calibration_brief_md_path,
        )
    except Exception as error:
        failure_record = None
        if progress.has_active_stage:
            failure_record = progress.fail(error)
            _emit_extraction_failure_context(progress=progress, error=error)
        if can_persist_operator_outputs:
            failure_final_outputs = _build_failure_final_outputs(
                settings=settings,
                run_id=run_id,
                score_run_id=resolved_score_run_id,
                decision_surface_run_id=resolved_decision_surface_run_id,
                manifest_path=manifest_path,
                error=error,
            )
            failure_outcome = classify_commercial_outcome(
                CommercialOutcomeInput(
                    run_completed_successfully_flag=False,
                    stage12_publish_status="",
                    stage12_publish_status_reason="",
                    stage12_pos_upload_row_count=0,
                    stage12_candidate_row_count=0,
                    stage12_duplicate_registry_skip_count=0,
                    stage13_validation_status="",
                    stage13_validation_status_reason="",
                    stage13_skip_class="",
                    runtime_failure_reason=type(error).__name__,
                )
            )
            commercial_run_outcome_summary_path = settings.artifacts.commercial_run_outcome_summary_path(run_id)
            commercial_run_outcome_summary_path.parent.mkdir(parents=True, exist_ok=True)
            commercial_run_outcome_summary_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "as_of_date": settings.as_of_date.isoformat(),
                        "proof_mode_flag": False,
                        "highest_stage_reached": int(failure_record.stage_number) if failure_record is not None else 0,
                        "completed_successfully_flag": False,
                        "commercial_outcome_class": failure_outcome.commercial_outcome_class,
                        "commercial_outcome_reason": failure_outcome.commercial_outcome_reason,
                        "commercial_outcome_message": failure_outcome.commercial_outcome_message,
                        "stage11_row_count": 0,
                        "stage12_candidate_row_count": 0,
                        "stage12_pos_upload_row_count": 0,
                        "stage12_excluded_row_count": 0,
                        "stage12_duplicate_registry_skip_count": 0,
                        "validation_status": "NOT_AVAILABLE",
                        "validation_status_reason": "runtime_failed_before_stage13_completion",
                        "operator_summary_json_path": str(settings.artifacts.operator_summary_path(run_id)),
                        "store_prediction_download_manifest_path": _optional_existing_output_path(
                            settings.artifacts.store_prediction_manifest_path(run_id)
                        ),
                        "publication_summary_csv_path": _optional_existing_output_path(
                            settings.artifacts.commercial_publication_summary_csv_path(run_id)
                        ),
                        "validation_manifest_path": _optional_existing_output_path(
                            settings.artifacts.validation_manifest_path(run_id)
                        ),
                        "decision_surface_manifest_path": _optional_existing_output_path(
                            settings.artifacts.decision_surface_manifest_path(resolved_decision_surface_run_id)
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            failure_final_outputs.update(
                {
                    "commercial_outcome_class": failure_outcome.commercial_outcome_class,
                    "commercial_outcome_reason": failure_outcome.commercial_outcome_reason,
                    "commercial_outcome_message": failure_outcome.commercial_outcome_message,
                    "commercial_new_publication_count": str(failure_outcome.commercial_new_publication_count),
                    "commercial_noop_flag": str(failure_outcome.commercial_noop_flag).lower(),
                    "commercial_failure_flag": str(failure_outcome.commercial_failure_flag).lower(),
                    "commercial_run_outcome_summary_path": str(commercial_run_outcome_summary_path),
                }
            )
            progress.emit_final_outputs(outputs=failure_final_outputs)
            operator_artifacts = progress.persist(
                status="failed",
                final_outputs=failure_final_outputs,
            )
            manifest_payload = _build_failure_manifest_payload(
                settings=settings,
                run_id=run_id,
                score_run_id=resolved_score_run_id,
                decision_surface_run_id=resolved_decision_surface_run_id,
                execution_mode=execution_mode,
                manifest_payload=manifest_payload,
                nas_bootstrap_artifacts=nas_bootstrap_artifacts,
                effective_completed_partitioning=effective_completed_partitioning,
                completed_partition_retry_records=completed_partition_retry_records,
                operator_artifacts=operator_artifacts,
                failure_record=failure_record,
                final_outputs=failure_final_outputs,
            )
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        raise


def _complete_zero_future_scored_rows_noop(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    score_run_id: str,
    decision_surface_run_id: str,
    execution_mode: str,
    target_mode: str | None,
    resolved_target_mode: str,
    manifest_path: Path,
    nas_bootstrap_artifacts: PromotionNasBootstrapArtifacts | None,
    completed_extraction: PromotionOperationalCycleExtractionArtifacts,
    future_extraction: PromotionOperationalCycleExtractionArtifacts,
    dataset,
    training_artifacts,
    scoring_artifacts,
    reporting_artifacts,
    progress: PromotionOperatorProgress,
    requested_completed_partitioning: PromotionCompletedPartitionSettings | None,
    effective_completed_partitioning: PromotionCompletedPartitionSettings | None,
    completed_partition_retry_records: list[PromotionCompletedPartitionRetryRecord],
    completed_partition_retries_json_path: str,
    completed_partition_retries_csv_path: str,
    stage6_plan,
    stage6_guardrail_path: str | None,
    stage6_plan_path: str | None,
) -> PromotionOperationalCycleArtifacts:
    stage13_skip_class, stage13_skip_reason = classify_stage13_validation_skip(
        stage12_publish_status=PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
        stage13_review_paths_present=False,
        stage13_pos_paths_present=False,
        stage13_reconciliation_paths_present=False,
    )
    commercial_outcome = classify_commercial_outcome(
        CommercialOutcomeInput(
            run_completed_successfully_flag=True,
            stage12_publish_status=PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
            stage12_publish_status_reason=ZERO_FUTURE_SCORED_ROWS_REASON,
            stage12_pos_upload_row_count=0,
            stage12_candidate_row_count=0,
            stage12_duplicate_registry_skip_count=0,
            stage13_validation_status="SKIPPED_NO_NEW_PUBLICATIONS",
            stage13_validation_status_reason=stage13_skip_reason,
            stage13_skip_class=stage13_skip_class,
        )
    )
    noop_summary_path = (
        settings.artifacts.manifests_run_root(run_id) / "zero_future_scored_rows_noop_summary.json"
    )
    commercial_run_outcome_summary_path = settings.artifacts.commercial_run_outcome_summary_path(run_id)
    publication_freshness_diagnostic_path = settings.artifacts.publication_freshness_diagnostic_path(run_id)
    validation_skip_summary_path = settings.artifacts.validation_skip_summary_path(run_id)

    publication_freshness_diagnostic = build_commercial_outcome_freshness_diagnostic(
        candidate_row_count=0,
        duplicate_registry_skip_count=0,
    ).to_dict()
    publication_freshness_diagnostic.update(
        {
            "run_id": run_id,
            "as_of_date": settings.as_of_date.isoformat(),
            "noop_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
            "stage8_skipped_flag": True,
        }
    )
    publication_freshness_diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
    publication_freshness_diagnostic_path.write_text(
        json.dumps(publication_freshness_diagnostic, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    validation_skip_summary = {
        "run_id": run_id,
        "as_of_date": settings.as_of_date.isoformat(),
        "validation_status": "SKIPPED_NO_NEW_PUBLICATIONS",
        "validation_status_reason": stage13_skip_reason,
        "validation_skipped_flag": True,
        "stage13_skip_class": stage13_skip_class,
        "stage13_skip_reason": stage13_skip_reason,
        "stage12_publish_status": PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
        "stage12_publish_status_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
    }
    validation_skip_summary_path.parent.mkdir(parents=True, exist_ok=True)
    validation_skip_summary_path.write_text(
        json.dumps(validation_skip_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    commercial_outcome_summary = {
        "run_id": run_id,
        "as_of_date": settings.as_of_date.isoformat(),
        "proof_mode_flag": False,
        "highest_stage_reached": 7,
        "completed_successfully_flag": True,
        "operational_noop_flag": True,
        "operational_noop_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
        "commercial_outcome_class": commercial_outcome.commercial_outcome_class,
        "commercial_outcome_reason": commercial_outcome.commercial_outcome_reason,
        "commercial_outcome_message": commercial_outcome.commercial_outcome_message,
        "commercial_new_publication_count": commercial_outcome.commercial_new_publication_count,
        "commercial_noop_flag": commercial_outcome.commercial_noop_flag,
        "commercial_failure_flag": commercial_outcome.commercial_failure_flag,
        "stage8_skipped_flag": True,
        "stage8_skip_class": ZERO_FUTURE_SCORED_ROWS_SKIP_CLASS,
        "stage8_skip_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
        "stage11_row_count": 0,
        "stage12_publish_status": PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
        "stage12_publish_status_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
        "stage12_candidate_row_count": 0,
        "stage12_pos_upload_row_count": 0,
        "stage12_excluded_row_count": 0,
        "stage12_duplicate_registry_skip_count": 0,
        "validation_status": "SKIPPED_NO_NEW_PUBLICATIONS",
        "validation_status_reason": stage13_skip_reason,
        "stage13_skip_class": stage13_skip_class,
        "validation_skip_summary_path": str(validation_skip_summary_path),
        "operator_summary_json_path": str(settings.artifacts.operator_summary_path(run_id)),
        "store_prediction_download_manifest_path": ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        "publication_summary_csv_path": ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        "validation_manifest_path": ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        "decision_surface_manifest_path": ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
    }
    commercial_run_outcome_summary_path.parent.mkdir(parents=True, exist_ok=True)
    commercial_run_outcome_summary_path.write_text(
        json.dumps(commercial_outcome_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    noop_summary = {
        "run_id": run_id,
        "score_run_id": score_run_id,
        "decision_surface_run_id": decision_surface_run_id,
        "as_of_date": settings.as_of_date.isoformat(),
        "noop_class": ZERO_FUTURE_SCORED_ROWS_SKIP_CLASS,
        "noop_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
        "noop_outcome_class": commercial_outcome.commercial_outcome_class,
        "noop_publish_status": PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
        "future_scored_row_count": 0,
        "skipped_stage_numbers": list(ZERO_FUTURE_SCORED_ROWS_SKIPPED_STAGE_NUMBERS),
        "skipped_stages": (
            "decision_surface",
            "inspection",
            "audit",
            "store_prediction_download",
            "commercial_publication",
            "validation",
            "final_publication_outputs",
        ),
        "scoring_manifest_path": scoring_artifacts.manifest_path,
        "commercial_run_outcome_summary_path": str(commercial_run_outcome_summary_path),
        "publication_freshness_diagnostic_path": str(publication_freshness_diagnostic_path),
        "validation_skip_summary_path": str(validation_skip_summary_path),
    }
    noop_summary_path.parent.mkdir(parents=True, exist_ok=True)
    noop_summary_path.write_text(
        json.dumps(noop_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    final_outputs = {
        "operational_cycle_manifest_path": str(manifest_path),
        "completed_base_path": completed_extraction.base_path,
        "completed_base_manifest_path": completed_extraction.manifest_path,
        "completed_partition_retries_json_path": completed_partition_retries_json_path,
        "completed_partition_retries_csv_path": completed_partition_retries_csv_path,
        "future_base_path": future_extraction.base_path,
        "future_base_manifest_path": future_extraction.manifest_path,
        "dataset_manifest_path": dataset.manifest_path,
        "model_manifest_path": training_artifacts.manifest_path,
        "scoring_manifest_path": scoring_artifacts.manifest_path,
        "score_report_manifest_path": reporting_artifacts.report_paths["report_manifest"],
        "zero_future_scored_rows_noop_summary_path": str(noop_summary_path),
        "publication_freshness_diagnostic_path": str(publication_freshness_diagnostic_path),
        "validation_skip_summary_path": str(validation_skip_summary_path),
        "commercial_run_outcome_summary_path": str(commercial_run_outcome_summary_path),
        "decision_surface_status": "skipped",
        "stage8_skip_class": ZERO_FUTURE_SCORED_ROWS_SKIP_CLASS,
        "stage8_skip_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
        "skipped_stage_numbers": ",".join(
            str(stage_number) for stage_number in ZERO_FUTURE_SCORED_ROWS_SKIPPED_STAGE_NUMBERS
        ),
        "stage12_publish_status": PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
        "stage12_publish_status_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
        "stage13_skip_class": stage13_skip_class,
        "stage13_skip_reason": stage13_skip_reason,
        "commercial_outcome_class": commercial_outcome.commercial_outcome_class,
        "commercial_outcome_reason": commercial_outcome.commercial_outcome_reason,
        "commercial_outcome_message": commercial_outcome.commercial_outcome_message,
        "commercial_new_publication_count": str(commercial_outcome.commercial_new_publication_count),
        "commercial_noop_flag": str(commercial_outcome.commercial_noop_flag).lower(),
        "commercial_failure_flag": str(commercial_outcome.commercial_failure_flag).lower(),
        "operator_log_path": str(settings.artifacts.operator_log_path(run_id)),
        "operator_summary_json_path": str(settings.artifacts.operator_summary_path(run_id)),
        "operator_summary_csv_path": str(settings.artifacts.operator_summary_csv_path(run_id)),
        "operator_stage_timings_path": str(settings.artifacts.operator_stage_timings_path(run_id)),
    }
    progress.detail(
        "governed_noop: zero future scored rows persisted at Stage 7; "
        "skipping Stages 8-14 without invoking the decision surface"
    )
    progress.emit_final_outputs(outputs=final_outputs)
    operator_artifacts = progress.persist(status="completed", final_outputs=final_outputs)

    manifest_payload = PromotionOperationalCycleManifest(
        run_id=run_id,
        score_run_id=score_run_id,
        decision_surface_run_id=decision_surface_run_id,
        executed_at_utc=datetime.now(tz=UTC).isoformat(),
        as_of_date=settings.as_of_date.isoformat(),
        artifact_root=str(settings.artifacts.root),
        nas_root=str(settings.artifacts.root),
        local_inspection_root=(
            str(settings.artifacts.local_inspection_root)
            if settings.artifacts.local_inspection_root is not None
            else None
        ),
        execution_mode=execution_mode,
        runtime_settings={
            "server": settings.sql.server,
            "database": settings.sql.database,
            "schema": settings.sql.schema,
            "promotion_advice_table": settings.sql.promotion_advice_table,
            "pwlogd_table": settings.sql.pwlogd_table,
            "odbc_driver": settings.sql.odbc_driver,
            "connect_timeout_seconds": settings.sql.connect_timeout_seconds,
            "connect_retry_attempts": settings.sql.connect_retry_attempts,
            "connect_retry_backoff_seconds": settings.sql.connect_retry_backoff_seconds,
            "query_timeout_seconds": settings.sql.query_timeout_seconds,
            "encrypt": settings.sql.encrypt,
            "trust_server_certificate": settings.sql.trust_server_certificate,
            "requested_target_mode": target_mode,
            "resolved_target_mode": resolved_target_mode,
            "requested_completed_partitioning": (
                requested_completed_partitioning.to_dict()
                if requested_completed_partitioning is not None
                else None
            ),
            "completed_partitioning": (
                effective_completed_partitioning.to_dict()
                if effective_completed_partitioning is not None
                else None
            ),
            "completed_extraction_runtime": settings.completed_extraction_runtime.to_dict(),
            "completed_preflight_planner": settings.completed_preflight_planner.to_dict(),
        },
        nas_bootstrap=nas_bootstrap_artifacts.to_dict() if nas_bootstrap_artifacts else None,
        completed_extraction={
            "run_id": run_id,
            "selection_mode": completed_extraction.selection_mode,
            "extraction_mode": completed_extraction.extraction_mode,
            "base_path": completed_extraction.base_path,
            "manifest_path": completed_extraction.manifest_path,
            "partition_summary_path": completed_extraction.partition_summary_path,
            "rendered_sql_path": completed_extraction.rendered_sql_path,
            "rendered_sql_parameters_path": completed_extraction.rendered_sql_parameters_path,
            "telemetry_json_path": completed_extraction.telemetry_json_path,
            "telemetry_csv_path": completed_extraction.telemetry_csv_path,
            "sql_diagnostics_summary_json_path": completed_extraction.diagnostics_summary_json_path,
            "sql_diagnostics_summary_txt_path": completed_extraction.diagnostics_summary_txt_path,
            "candidate_promotion_row_count": completed_extraction.candidate_promotion_row_count,
            "manifest": completed_extraction.manifest,
            "partition_retries_json_path": completed_partition_retries_json_path,
            "partition_retries_csv_path": completed_partition_retries_csv_path,
            "repartition_attempt_count": len(completed_partition_retry_records),
        },
        training_dataset={
            "run_id": run_id,
            "dataset_path": dataset.dataset_path,
            "manifest_path": dataset.manifest_path,
            "manifest": dataset.manifest.to_dict(),
        },
        model_bundle={
            "run_id": run_id,
            "artifact_root": training_artifacts.artifact_root,
            "manifest_path": training_artifacts.manifest_path,
            "metrics_path": training_artifacts.metrics_path,
            "inference_schema_path": training_artifacts.inference_schema_path,
            "feature_list_path": training_artifacts.feature_list_path,
            "target_mode": training_artifacts.target_mode,
            "artifact_files": training_artifacts.artifact_files,
        },
        future_extraction={
            "run_id": score_run_id,
            "selection_mode": future_extraction.selection_mode,
            "extraction_mode": future_extraction.extraction_mode,
            "partition_strategy": future_extraction.partition_strategy,
            "partition_count": future_extraction.partition_count,
            "partition_index": future_extraction.partition_index,
            "base_path": future_extraction.base_path,
            "manifest_path": future_extraction.manifest_path,
            "partition_summary_path": future_extraction.partition_summary_path,
            "rendered_sql_path": future_extraction.rendered_sql_path,
            "rendered_sql_parameters_path": future_extraction.rendered_sql_parameters_path,
            "telemetry_json_path": future_extraction.telemetry_json_path,
            "telemetry_csv_path": future_extraction.telemetry_csv_path,
            "sql_diagnostics_summary_json_path": future_extraction.diagnostics_summary_json_path,
            "sql_diagnostics_summary_txt_path": future_extraction.diagnostics_summary_txt_path,
            "candidate_promotion_row_count": future_extraction.candidate_promotion_row_count,
            "manifest": future_extraction.manifest,
            "stage6_execution_scope": stage6_plan.execution_scope,
            "stage6_planner_verdict": stage6_plan.planner_verdict,
            "stage6_operator_message": stage6_plan.operator_message,
            "stage6_guardrail_reason": stage6_plan.guardrail_reason,
            "stage6_future_extraction_mode": stage6_plan.future_extraction_mode,
            "stage6_proof_max_future_promotions": stage6_plan.proof_max_future_promotions,
            "stage6_proof_fallback_used": stage6_plan.proof_fallback_used,
            "stage6_proof_fallback_mode": stage6_plan.proof_fallback_mode,
            "stage6_proof_fallback_reason": stage6_plan.proof_fallback_reason,
            "stage6_proof_bounding_supported_flag": stage6_plan.proof_bounding_supported_flag,
            "stage6_proof_bounding_reason": stage6_plan.proof_bounding_reason,
            "stage6_future_query_options": _serialize_stage6_query_options(
                stage6_plan.future_query_options
            ),
            "stage6_future_extraction_guardrail_path": stage6_guardrail_path,
            "stage6_future_extraction_plan_path": stage6_plan_path,
        },
        scoring={
            "run_id": score_run_id,
            "row_count": 0,
            "manifest_path": scoring_artifacts.manifest_path,
            "row_predictions_path": scoring_artifacts.row_predictions_path,
            "summary_paths": scoring_artifacts.summary_paths,
            "report_paths": reporting_artifacts.report_paths,
        },
        decision_surface={
            "run_id": decision_surface_run_id,
            "status": "skipped",
            "skip_class": ZERO_FUTURE_SCORED_ROWS_SKIP_CLASS,
            "skip_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
            "manifest_path": ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
            "execution_summary_path": ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
            "inspection_manifest_path": ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        },
        store_outputs={
            "status": "skipped",
            "skip_class": ZERO_FUTURE_SCORED_ROWS_SKIP_CLASS,
            "skip_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
            "stage11_row_count": 0,
            "stage12_publish_status": PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
            "stage12_publish_status_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
            "stage12_candidate_row_count": 0,
            "stage12_pos_upload_row_count": 0,
        },
        operator_progress=operator_artifacts.to_dict(),
        final_outputs=final_outputs,
    ).to_dict()
    manifest_payload["operational_noop"] = noop_summary
    manifest_payload["commercial_execution_outputs"] = {
        "commercial_run_outcome_summary_path": str(commercial_run_outcome_summary_path),
        "publication_freshness_diagnostic_path": str(publication_freshness_diagnostic_path),
        "validation_skip_summary_path": str(validation_skip_summary_path),
        "stage12_publish_status": PUBLISH_STATUS_NOOP_VALID_NO_PUBLISHABLE_ROWS,
        "stage12_publish_status_reason": ZERO_FUTURE_SCORED_ROWS_REASON,
        "commercial_outcome_class": commercial_outcome.commercial_outcome_class,
        "commercial_outcome_reason": commercial_outcome.commercial_outcome_reason,
        "commercial_noop_flag": commercial_outcome.commercial_noop_flag,
        "commercial_failure_flag": commercial_outcome.commercial_failure_flag,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")

    return PromotionOperationalCycleArtifacts(
        manifest_path=str(manifest_path),
        nas_bootstrap_summary_path=(
            nas_bootstrap_artifacts.summary_path if nas_bootstrap_artifacts else "unavailable"
        ),
        nas_root=str(settings.artifacts.root),
        local_inspection_root=(
            str(settings.artifacts.local_inspection_root)
            if settings.artifacts.local_inspection_root is not None
            else None
        ),
        completed_base_path=completed_extraction.base_path,
        completed_base_manifest_path=completed_extraction.manifest_path,
        completed_partition_summary_path=completed_extraction.partition_summary_path,
        future_base_path=future_extraction.base_path,
        future_base_manifest_path=future_extraction.manifest_path,
        dataset_path=dataset.dataset_path,
        dataset_manifest_path=dataset.manifest_path,
        model_manifest_path=training_artifacts.manifest_path,
        scoring_manifest_path=scoring_artifacts.manifest_path,
        score_report_manifest_path=reporting_artifacts.report_paths["report_manifest"],
        decision_surface_manifest_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        decision_surface_execution_summary_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        decision_surface_inspection_manifest_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        inspection_review_packet_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        store_prediction_master_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        store_prediction_download_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        store_prediction_per_store_csv_paths=(),
        store_prediction_per_store_promotion_csv_paths=(),
        store_prediction_reconciliation_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        store_prediction_manifest_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        store_prediction_manifest_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_prediction_registry_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_prediction_manifest_paths=(),
        commercial_pos_upload_paths=(),
        commercial_review_paths=(),
        commercial_summary_paths=(),
        commercial_reconciliation_paths=(),
        commercial_publication_summary_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_diagnostics_paths=(
            str(noop_summary_path),
            str(publication_freshness_diagnostic_path),
            str(validation_skip_summary_path),
        ),
        commercial_skipped_paths=(str(noop_summary_path), str(validation_skip_summary_path)),
        pilot_validation_summary_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        pilot_validation_summary_json_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        pilot_validation_failures_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        gold_standard_acceptance_results_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        gold_standard_acceptance_results_json_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        validation_manifest_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        validation_skip_summary_path=str(validation_skip_summary_path),
        commercial_run_outcome_summary_path=str(commercial_run_outcome_summary_path),
        publication_freshness_diagnostic_path=str(publication_freshness_diagnostic_path),
        commercial_delta_summary_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_delta_top_changes_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_delta_store_summary_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_change_explanations_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_priority_queue_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_action_summary_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_outcome_attribution_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        recommendation_effectiveness_summary_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        recommendation_effectiveness_by_reason_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        recommendation_learning_priority_queue_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_policy_calibration_summary_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_policy_calibration_by_segment_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_policy_watchlist_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_policy_calibration_brief_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_policy_simulation_summary_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_policy_simulation_by_segment_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_policy_simulation_watchlist_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_policy_simulation_brief_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_action_instruction_summary_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_action_priority_queue_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_action_by_segment_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        commercial_action_instruction_brief_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        local_store_prediction_download_path=None,
        local_decision_surface_csv_path=None,
        local_review_packet_csv_path=None,
        local_run_summary_path=None,
        audit_manifest_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        audit_summary_json_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        audit_summary_csv_path=ZERO_FUTURE_SCORED_ROWS_PLACEHOLDER,
        operator_log_path=operator_artifacts.log_path,
        operator_summary_path=operator_artifacts.summary_path,
        operator_summary_csv_path=operator_artifacts.summary_csv_path,
        operator_stage_timings_path=operator_artifacts.stage_timings_path,
    )


def _build_failure_final_outputs(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    score_run_id: str,
    decision_surface_run_id: str,
    manifest_path: Path,
    error: BaseException,
) -> dict[str, str]:
    completed_partition_summary_default = _optional_existing_output_path(
        settings.artifacts.completed_partition_summary_path(run_id)
    )
    stage6_guardrail_default = _optional_existing_output_path(
        settings.artifacts.manifests_run_root(score_run_id)
        / "stage6_future_extraction_guardrail.json"
    )
    stage6_plan_default = _optional_existing_output_path(
        settings.artifacts.manifests_run_root(score_run_id) / "stage6_future_extraction_plan.json"
    )
    stage6_failure_summary_default = _optional_existing_output_path(
        settings.artifacts.manifests_run_root(score_run_id)
        / "stage6_future_extraction_failure_summary.json"
    )
    return {
        "operational_cycle_manifest_path": str(manifest_path),
        "operator_log_path": str(settings.artifacts.operator_log_path(run_id)),
        "operator_summary_json_path": str(settings.artifacts.operator_summary_path(run_id)),
        "operator_summary_csv_path": str(settings.artifacts.operator_summary_csv_path(run_id)),
        "completed_partition_retries_json_path": _optional_existing_output_path(
            settings.artifacts.completed_partition_retries_json_path(run_id)
        ),
        "completed_partition_retries_csv_path": _optional_existing_output_path(
            settings.artifacts.completed_partition_retries_csv_path(run_id)
        ),
        "completed_preflight_cost_diagnostic_path": _optional_error_output_path(
            error,
            "completed_preflight_cost_diagnostic_path",
            fallback=_optional_existing_output_path(
                settings.artifacts.completed_preflight_cost_diagnostic_path(run_id)
            ),
        ),
        "completed_preflight_model_learning_diagnostic_path": _optional_error_output_path(
            error,
            "completed_preflight_model_learning_diagnostic_path",
            fallback=_optional_existing_output_path(
                settings.artifacts.completed_preflight_model_learning_diagnostic_path(run_id)
            ),
        ),
        "completed_proof_fallback_used": str(
            bool(getattr(error, "completed_proof_fallback_used", False))
        ).lower(),
        "completed_proof_fallback_mode": (
            getattr(error, "completed_proof_fallback_mode", None) or "none"
        ),
        "completed_proof_fallback_reason": (
            getattr(error, "completed_proof_fallback_reason", None) or "none"
        ),
        "store_prediction_download_path": _optional_existing_output_path(
            settings.artifacts.store_prediction_download_path(
                run_id=score_run_id,
                as_of_date=settings.as_of_date.isoformat(),
            )
        ),
        "decision_surface_csv_path": _optional_existing_output_path(
            settings.artifacts.decision_surface_run_root(decision_surface_run_id)
            / "inspection"
            / "decision_surface_records.csv"
        ),
        "inspection_review_packet_csv_path": _optional_existing_output_path(
            settings.artifacts.decision_surface_run_root(decision_surface_run_id)
            / "inspection"
            / "review_packet.csv"
        ),
        "completed_partition_summary_path": _optional_error_output_path(
            error,
            "completed_partition_summary_path",
            fallback=completed_partition_summary_default,
        ),
        "completed_preflight_summary_path": _optional_error_output_path(
            error,
            "preflight_summary_json_path",
        ),
        "completed_rendered_preflight_sql_path": _optional_error_output_path(
            error,
            "rendered_preflight_sql_path",
        ),
        "completed_rendered_preflight_sql_parameters_path": _optional_error_output_path(
            error,
            "rendered_preflight_sql_parameters_path",
        ),
        "completed_rendered_sql_path": _optional_error_output_path(error, "rendered_sql_path"),
        "completed_rendered_sql_parameters_path": _optional_error_output_path(
            error,
            "rendered_sql_parameters_path",
        ),
        "stage3_completed_extraction_failure_summary_path": _optional_error_output_path(
            error,
            "stage3_completed_extraction_failure_summary_path",
        ),
        "stage3_completed_extraction_exception_chain_path": _optional_error_output_path(
            error,
            "stage3_completed_extraction_exception_chain_path",
        ),
        "stage3_completed_extraction_guardrail_path": _optional_error_output_path(
            error,
            "stage3_completed_extraction_guardrail_path",
        ),
        "stage6_future_extraction_guardrail_path": _optional_error_output_path(
            error,
            "stage6_future_extraction_guardrail_path",
            fallback=stage6_guardrail_default,
        ),
        "stage6_future_extraction_plan_path": _optional_error_output_path(
            error,
            "stage6_future_extraction_plan_path",
            fallback=stage6_plan_default,
        ),
        "stage6_future_extraction_failure_summary_path": _optional_error_output_path(
            error,
            "stage6_future_extraction_failure_summary_path",
            fallback=stage6_failure_summary_default,
        ),
        "stage6_execution_scope": getattr(error, "stage6_execution_scope", None) or "none",
        "stage6_planner_verdict": getattr(error, "stage6_planner_verdict", None) or "none",
        "stage6_future_extraction_mode": (
            getattr(error, "stage6_future_extraction_mode", None) or "none"
        ),
        "stage6_proof_fallback_used": str(
            bool(getattr(error, "stage6_proof_fallback_used", False))
        ).lower(),
        "stage6_proof_fallback_mode": (
            getattr(error, "stage6_proof_fallback_mode", None) or "none"
        ),
        "stage6_proof_fallback_reason": (
            getattr(error, "stage6_proof_fallback_reason", None) or "none"
        ),
    }


def _stage6_success_final_output_fields(
    *,
    stage6_plan: _Stage6ExecutionPlan,
    stage6_guardrail_path: str | None,
    stage6_plan_path: str | None,
    stage6_failure_summary_path: str | None,
) -> dict[str, str]:
    return {
        "stage6_execution_scope": stage6_plan.execution_scope,
        "stage6_planner_verdict": stage6_plan.planner_verdict,
        "stage6_future_extraction_mode": stage6_plan.future_extraction_mode,
        "stage6_proof_max_future_promotions": (
            str(stage6_plan.proof_max_future_promotions)
            if stage6_plan.proof_max_future_promotions is not None
            else "none"
        ),
        "stage6_proof_fallback_used": str(stage6_plan.proof_fallback_used).lower(),
        "stage6_proof_fallback_mode": stage6_plan.proof_fallback_mode or "none",
        "stage6_proof_fallback_reason": stage6_plan.proof_fallback_reason or "none",
        "stage6_future_extraction_guardrail_path": stage6_guardrail_path or "unavailable",
        "stage6_future_extraction_plan_path": stage6_plan_path or "unavailable",
        "stage6_future_extraction_failure_summary_path": (
            stage6_failure_summary_path or "not_generated"
        ),
    }


def _build_failure_manifest_payload(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    score_run_id: str,
    decision_surface_run_id: str,
    execution_mode: str,
    manifest_payload: dict[str, object] | None,
    nas_bootstrap_artifacts: PromotionNasBootstrapArtifacts | None,
    effective_completed_partitioning: PromotionCompletedPartitionSettings | None,
    completed_partition_retry_records: list[PromotionCompletedPartitionRetryRecord],
    operator_artifacts: PromotionOperatorProgressArtifacts,
    failure_record: PromotionOperatorStageRecord | None,
    final_outputs: dict[str, str],
) -> dict[str, object]:
    payload = dict(manifest_payload) if manifest_payload is not None else {
        "run_id": run_id,
        "score_run_id": score_run_id,
        "decision_surface_run_id": decision_surface_run_id,
        "executed_at_utc": datetime.now(tz=UTC).isoformat(),
        "as_of_date": settings.as_of_date.isoformat(),
        "artifact_root": str(settings.artifacts.root),
        "nas_root": str(settings.artifacts.root),
        "local_inspection_root": (
            str(settings.artifacts.local_inspection_root)
            if settings.artifacts.local_inspection_root is not None
            else None
        ),
        "execution_mode": execution_mode,
        "runtime_settings": {
            "server": settings.sql.server,
            "database": settings.sql.database,
            "schema": settings.sql.schema,
            "promotion_advice_table": settings.sql.promotion_advice_table,
            "pwlogd_table": settings.sql.pwlogd_table,
            "odbc_driver": settings.sql.odbc_driver,
            "connect_timeout_seconds": settings.sql.connect_timeout_seconds,
            "connect_retry_attempts": settings.sql.connect_retry_attempts,
            "connect_retry_backoff_seconds": settings.sql.connect_retry_backoff_seconds,
            "query_timeout_seconds": settings.sql.query_timeout_seconds,
            "encrypt": settings.sql.encrypt,
            "trust_server_certificate": settings.sql.trust_server_certificate,
            "requested_completed_partitioning": (
                settings.completed_partitioning.to_dict()
                if settings.completed_partitioning is not None
                else None
            ),
            "completed_partitioning": (
                effective_completed_partitioning.to_dict()
                if effective_completed_partitioning is not None
                else None
            ),
            "completed_extraction_runtime": settings.completed_extraction_runtime.to_dict(),
            "completed_preflight_planner": settings.completed_preflight_planner.to_dict(),
        },
        "nas_bootstrap": None,
        "completed_extraction": {
            "selection_mode": "completed",
            "partition_strategy": _partition_strategy_value(effective_completed_partitioning),
            "partition_count": _partition_count_value(effective_completed_partitioning),
            "partition_summary_path": final_outputs.get("completed_partition_summary_path"),
            "estimated_cost_score": None,
            "cost_guardrail_verdict": None,
            "cost_guardrail_reason": None,
            "partition_retries_json_path": str(
                settings.artifacts.completed_partition_retries_json_path(run_id)
            ),
            "partition_retries_csv_path": str(
                settings.artifacts.completed_partition_retries_csv_path(run_id)
            ),
            "repartition_attempt_count": len(completed_partition_retry_records),
        },
        "training_dataset": None,
        "model_bundle": None,
        "future_extraction": None,
        "scoring": None,
        "decision_surface": None,
        "store_outputs": None,
        "local_inspection": None,
        "audit": None,
        "operator_progress": None,
        "final_outputs": None,
        "failure": None,
    }
    payload["nas_bootstrap"] = (
        nas_bootstrap_artifacts.to_dict() if nas_bootstrap_artifacts is not None else payload.get("nas_bootstrap")
    )
    payload["operator_progress"] = operator_artifacts.to_dict()
    payload["final_outputs"] = final_outputs
    if failure_record is not None:
        payload["failure"] = failure_record.to_dict()
    return payload


def _optional_existing_output_path(path: str | Path) -> str:
    resolved_path = Path(path)
    return str(resolved_path) if resolved_path.exists() else "unavailable"


def _optional_error_output_path(
    error: BaseException,
    attribute_name: str,
    fallback: str = "unavailable",
) -> str:
    value = getattr(error, attribute_name, None)
    if value in (None, ""):
        return fallback
    return str(value)


def _unique_output_paths(*paths: str | Path | None) -> tuple[str, ...]:
    """Return stable ordered unique output paths for operator-readable reporting."""
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path is None:
            continue
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return tuple(ordered)


def _build_partial_operational_cycle_artifacts(
    *,
    run_id: str,
    settings: PromotionPipelineSettings,
    nas_bootstrap_artifacts: PromotionNasBootstrapArtifacts | None,
    local_inspection_artifacts: PromotionLocalInspectionArtifacts | None,
    completed_extraction: PromotionOperationalCycleExtractionArtifacts,
    dataset: PromotionDatasetAssembler.PromotionDatasetArtifacts | None = None,
    progress: PromotionOperatorProgress | None = None,
    stop_after_stage: int | None = None,
) -> PromotionOperationalCycleArtifacts:
    """Build partial artifacts for early termination in proof-mode runs."""
    
    # Construct placeholder paths for downstream stages that won't run
    resolved_score_run_id = f"{run_id}-score"
    resolved_decision_surface_run_id = f"{run_id}-decision-surface"
    
    return PromotionOperationalCycleArtifacts(
        manifest_path=settings.artifacts.operational_cycle_manifest_path(run_id),
        nas_bootstrap_summary_path=(
            nas_bootstrap_artifacts.summary_path if nas_bootstrap_artifacts else "unavailable"
        ),
        nas_root=str(settings.artifacts.root),
        local_inspection_root=(
            str(settings.artifacts.local_inspection_root)
            if settings.artifacts.local_inspection_root
            else None
        ),
        completed_base_path=completed_extraction.base_path,
        completed_base_manifest_path=completed_extraction.manifest_path,
        completed_partition_summary_path=completed_extraction.partition_summary_path,
        future_base_path="unavailable_proof_mode_stopped",
        future_base_manifest_path="unavailable_proof_mode_stopped",
        dataset_path=dataset.dataset_path if dataset else "unavailable",
        dataset_manifest_path=dataset.manifest_path if dataset else "unavailable",
        model_manifest_path="unavailable_proof_mode_stopped",
        scoring_manifest_path="unavailable_proof_mode_stopped",
        score_report_manifest_path="unavailable_proof_mode_stopped",
        decision_surface_manifest_path="unavailable_proof_mode_stopped",
        decision_surface_execution_summary_path="unavailable_proof_mode_stopped",
        decision_surface_inspection_manifest_path="unavailable_proof_mode_stopped",
        inspection_review_packet_csv_path="unavailable_proof_mode_stopped",
        store_prediction_master_csv_path="unavailable_proof_mode_stopped",
        store_prediction_download_path="unavailable_proof_mode_stopped",
        store_prediction_per_store_csv_paths=(),
        store_prediction_per_store_promotion_csv_paths=(),
        store_prediction_reconciliation_csv_path="unavailable_proof_mode_stopped",
        store_prediction_manifest_path="unavailable_proof_mode_stopped",
        store_prediction_manifest_csv_path="unavailable_proof_mode_stopped",
        commercial_prediction_registry_path="unavailable_proof_mode_stopped",
        commercial_prediction_manifest_paths=(),
        commercial_pos_upload_paths=(),
        commercial_review_paths=(),
        commercial_summary_paths=(),
        commercial_reconciliation_paths=(),
        commercial_publication_summary_path="unavailable_proof_mode_stopped",
        commercial_diagnostics_paths=(),
        commercial_skipped_paths=(),
        pilot_validation_summary_csv_path="unavailable_proof_mode_stopped",
        pilot_validation_summary_json_path="unavailable_proof_mode_stopped",
        pilot_validation_failures_csv_path="unavailable_proof_mode_stopped",
        gold_standard_acceptance_results_csv_path="unavailable_proof_mode_stopped",
        gold_standard_acceptance_results_json_path="unavailable_proof_mode_stopped",
        validation_manifest_path="unavailable_proof_mode_stopped",
        validation_skip_summary_path="unavailable_proof_mode_stopped",
        commercial_run_outcome_summary_path="unavailable_proof_mode_stopped",
        publication_freshness_diagnostic_path="unavailable_proof_mode_stopped",
        commercial_delta_summary_path="unavailable_proof_mode_stopped",
        commercial_delta_top_changes_csv_path="unavailable_proof_mode_stopped",
        commercial_delta_store_summary_csv_path="unavailable_proof_mode_stopped",
        commercial_change_explanations_csv_path="unavailable_proof_mode_stopped",
        commercial_priority_queue_csv_path="unavailable_proof_mode_stopped",
        commercial_action_summary_path="unavailable_proof_mode_stopped",
        commercial_outcome_attribution_csv_path="unavailable_proof_mode_stopped",
        recommendation_effectiveness_summary_path="unavailable_proof_mode_stopped",
        recommendation_effectiveness_by_reason_csv_path="unavailable_proof_mode_stopped",
        recommendation_learning_priority_queue_csv_path="unavailable_proof_mode_stopped",
        commercial_policy_calibration_summary_path="unavailable_proof_mode_stopped",
        commercial_policy_calibration_by_segment_csv_path="unavailable_proof_mode_stopped",
        commercial_policy_watchlist_csv_path="unavailable_proof_mode_stopped",
        commercial_policy_calibration_brief_path="unavailable_proof_mode_stopped",
        commercial_policy_simulation_summary_path="unavailable_proof_mode_stopped",
        commercial_policy_simulation_by_segment_csv_path="unavailable_proof_mode_stopped",
        commercial_policy_simulation_watchlist_csv_path="unavailable_proof_mode_stopped",
        commercial_policy_simulation_brief_path="unavailable_proof_mode_stopped",
        commercial_action_instruction_summary_path="unavailable_proof_mode_stopped",
        commercial_action_priority_queue_csv_path="unavailable_proof_mode_stopped",
        commercial_action_by_segment_csv_path="unavailable_proof_mode_stopped",
        commercial_action_instruction_brief_path="unavailable_proof_mode_stopped",
        local_store_prediction_download_path=(
            local_inspection_artifacts.store_prediction_download_path
            if local_inspection_artifacts
            else None
        ),
        local_decision_surface_csv_path=(
            local_inspection_artifacts.decision_surface_csv_path
            if local_inspection_artifacts
            else None
        ),
        local_review_packet_csv_path=(
            local_inspection_artifacts.review_packet_csv_path
            if local_inspection_artifacts
            else None
        ),
        local_run_summary_path=(
            local_inspection_artifacts.run_summary_path if local_inspection_artifacts else None
        ),
        audit_manifest_path="unavailable_proof_mode_stopped",
        audit_summary_json_path="unavailable_proof_mode_stopped",
        audit_summary_csv_path="unavailable_proof_mode_stopped",
        operator_log_path="unavailable",
        operator_summary_path="unavailable",
        operator_summary_csv_path="unavailable",
        operator_stage_timings_path="unavailable",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the governed promotions operational cycle.")
    parser.add_argument("--env-file")
    parser.add_argument("--server")
    parser.add_argument("--database")
    parser.add_argument("--schema")
    parser.add_argument("--promotion-advice-table")
    parser.add_argument("--pwlogd-table")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--odbc-driver")
    parser.add_argument("--connect-timeout-seconds", type=int)
    parser.add_argument("--connect-retry-attempts", type=int)
    parser.add_argument("--connect-retry-backoff-seconds", type=float)
    parser.add_argument("--query-timeout-seconds", type=int)
    parser.add_argument("--encrypt", choices=("yes", "no"))
    parser.add_argument("--trust-server-certificate", choices=("yes", "no"))
    parser.add_argument("--artifact-root")
    parser.add_argument("--local-inspection-root")
    parser.add_argument("--disable-local-inspection-copy", action="store_true")
    parser.add_argument("--as-of-date")
    parser.add_argument("--target-mode", choices=PROMOTION_TRAINER_TARGET_MODE_CHOICES)
    parser.add_argument(
        "--run-id",
        default=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    parser.add_argument("--score-run-id")
    parser.add_argument("--decision-surface-run-id")
    parser.add_argument(
        "--partition-strategy",
        choices=(
            "store_number",
            "supplier_number",
            "store_sku_hash_bucket",
            "promotion_name_hash_bucket",
            "promotion_row_key_hash_bucket",
        ),
    )
    parser.add_argument("--partition-count", type=int)
    parser.add_argument("--partition-index", type=int)
    parser.add_argument("--run-preflight", action="store_true")
    parser.add_argument(
        "--auto-repartition-completed",
        choices=("true", "false"),
        default="true",
    )
    parser.add_argument("--max-completed-repartition-attempts", type=int, default=3)
    parser.add_argument("--max-completed-partition-count", type=int, default=512)
    parser.add_argument("--proof-mode", action="store_true", help="Enable live-proof mode: real SQL extraction, real Stage 4 logic, but bounded")
    parser.add_argument("--proof-max-partitions", type=int, help="Cap effective partition count at this value for proof runs")
    parser.add_argument("--proof-stop-after-stage", type=int, help="Stop execution after this stage in proof-mode (1-14)")
    parser.add_argument("--proof-max-future-promotions", type=int, help="Bound Stage 6 future extraction to top-N rows for proof-mode runs")
    parser.add_argument(
        "--proof-future-fallback-mode",
        choices=("diagnostic_topn", "proof_slice"),
        help="In proof-mode only, Stage 6 fallback mode when no explicit future bound is supplied",
    )
    parser.add_argument(
        "--proof-future-fallback-topn-limit",
        type=int,
        help="In proof-mode Stage 6 diagnostic_topn fallback, top-N future promotions limit",
    )
    parser.add_argument(
        "--proof-future-fallback-slice-promotions",
        type=int,
        help="In proof-mode Stage 6 proof_slice fallback, bounded promotion count",
    )
    parser.add_argument(
        "--proof-completed-fallback-mode",
        choices=("diagnostic_topn", "proof_slice"),
        help="In proof-mode only, fallback mode when completed preflight rejects full scope",
    )
    parser.add_argument(
        "--proof-completed-fallback-topn-limit",
        type=int,
        help="In proof-mode fallback diagnostic_topn mode, top-N completed promotions limit",
    )
    parser.add_argument(
        "--proof-completed-fallback-slice-promotions",
        type=int,
        help="In proof-mode fallback proof_slice mode, bounded promotion count",
    )
    parser.add_argument("--enable-landed-batches", choices=("true", "false"))
    parser.add_argument("--batch-row-count", type=int)
    parser.add_argument("--completed-sales-history-start-date")
    parser.add_argument("--enable-chunked-fetch", choices=("true", "false"))
    parser.add_argument("--chunk-row-count", type=int)
    parser.add_argument("--resume-completed-partitions", choices=("true", "false"))
    parser.add_argument("--stage-temp-chunk-files", choices=("true", "false"))
    parser.add_argument("--max-candidate-promotion-rows", type=int)
    parser.add_argument("--max-candidate-store-sku", type=int)
    parser.add_argument("--max-window-span-days-total", type=int)
    parser.add_argument("--max-window-span-days-max", type=int)
    parser.add_argument("--planner-only", action="store_true")
    parser.add_argument("--minimum-cohort-sample-size", type=int, default=3)
    parser.add_argument("--similarity-threshold", type=float)
    parser.add_argument("--archetype-confidence-floor", type=float)
    parser.add_argument("--row-model-confidence-floor", type=float)
    return parser


def _build_settings(args: argparse.Namespace) -> PromotionPipelineSettings:
    runtime_date = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    artifact_paths = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
        local_inspection_root=(
            Path(args.local_inspection_root) if args.local_inspection_root else None
        ),
        enable_local_inspection_copy=not args.disable_local_inspection_copy,
        env_file=args.env_file,
    )
    return PromotionPipelineSettings.for_runtime_date(
        sql=PromotionMssqlSettings.from_env(
            promotion_advice_table=args.promotion_advice_table,
            pwlogd_table=args.pwlogd_table,
            env_file=args.env_file,
            server=args.server,
            database=args.database,
            schema=args.schema,
            username=args.username,
            password=args.password,
            odbc_driver=args.odbc_driver,
            connect_timeout_seconds=args.connect_timeout_seconds,
            connect_retry_attempts=args.connect_retry_attempts,
            connect_retry_backoff_seconds=args.connect_retry_backoff_seconds,
            query_timeout_seconds=args.query_timeout_seconds,
            encrypt=args.encrypt,
            trust_server_certificate=args.trust_server_certificate,
        ),
        runtime_date=runtime_date,
        artifacts=artifact_paths,
        completed_partitioning=_build_completed_partitioning_from_args(args),
        completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings.from_env(
            enable_landed_batches=args.enable_landed_batches,
            batch_row_count=args.batch_row_count,
            completed_sales_history_start_date=args.completed_sales_history_start_date,
            enable_chunked_fetch=args.enable_chunked_fetch,
            chunk_row_count=args.chunk_row_count,
            resume_completed_partitions=args.resume_completed_partitions,
            stage_temp_chunk_files=args.stage_temp_chunk_files,
            env_file=args.env_file,
        ),
        completed_preflight_planner=_build_completed_preflight_planner_from_args(args),
    )


def _should_use_chunked_completed_extraction(
    *,
    settings: PromotionPipelineSettings,
    selection_mode: str,
) -> bool:
    return (
        selection_mode == "completed"
        and not settings.completed_extraction_runtime.enable_landed_batches
        and settings.completed_extraction_runtime.enable_chunked_fetch
    )


def _should_use_landed_batch_completed_extraction(
    *,
    settings: PromotionPipelineSettings,
    selection_mode: str,
    query_options: PromotionBaseQueryOptions | None = None,
) -> bool:
    extraction_mode = query_options.extraction_mode if query_options is not None else "live_sql"
    return (
        selection_mode == "completed"
        and settings.completed_extraction_runtime.enable_landed_batches
        and extraction_mode == "live_sql"
    )


@dataclass(frozen=True)
class _Stage6ExecutionPlan:
    """Governed execution decision for Stage 6 future extraction."""

    execution_scope: str  # "proof_bounded_scope" | "full_scope"
    future_extraction_mode: str  # "diagnostic_topn" | "live_sql"
    proof_max_future_promotions: int | None
    future_query_options: PromotionBaseQueryOptions | None
    operator_message: str
    planner_verdict: str  # "PROOF_BOUNDED_SCOPE" | "PROOF_BOUNDED_FALLBACK" | "FULL_SCOPE"
    proof_bounding_supported_flag: bool
    proof_bounding_reason: str
    guardrail_reason: str
    proof_fallback_used: bool
    proof_fallback_mode: str | None
    proof_fallback_reason: str | None
    query_timeout_seconds: int | None

    @property
    def proof_bounded(self) -> bool:
        return self.execution_scope == "proof_bounded_scope"


def _plan_stage6_future_extraction(
    *,
    proof_mode: bool,
    proof_max_future_promotions: int | None,
    proof_future_fallback_mode: str | None = None,
    proof_future_fallback_topn_limit: int | None = None,
    proof_future_fallback_slice_promotions: int | None = None,
    query_timeout_seconds: int | None,
) -> _Stage6ExecutionPlan:
    """Produce the authoritative Stage 6 future-extraction execution plan."""
    if proof_max_future_promotions is not None and proof_max_future_promotions < 1:
        raise ValueError("proof_max_future_promotions must be >= 1 when provided.")
    if (
        proof_future_fallback_topn_limit is not None
        and proof_future_fallback_topn_limit < 1
    ):
        raise ValueError("proof_future_fallback_topn_limit must be >= 1 when provided.")
    if (
        proof_future_fallback_slice_promotions is not None
        and proof_future_fallback_slice_promotions < 1
    ):
        raise ValueError(
            "proof_future_fallback_slice_promotions must be >= 1 when provided."
        )
    if proof_future_fallback_mode is not None and proof_future_fallback_mode not in {
        "diagnostic_topn",
        "proof_slice",
    }:
        raise ValueError(
            "proof_future_fallback_mode must be 'diagnostic_topn' or 'proof_slice' when provided."
        )
    if not proof_mode and proof_max_future_promotions is not None:
        raise ValueError(
            "proof_max_future_promotions requires proof_mode=true. "
            "Either enable --proof-mode or remove --proof-max-future-promotions."
        )
    if not proof_mode and any(
        value is not None
        for value in (
            proof_future_fallback_mode,
            proof_future_fallback_topn_limit,
            proof_future_fallback_slice_promotions,
        )
    ):
        raise ValueError(
            "proof_future_fallback_* settings require proof_mode=true. "
            "Either enable --proof-mode or remove the Stage 6 proof fallback controls."
        )

    if proof_mode and proof_max_future_promotions is not None:
        return _Stage6ExecutionPlan(
            execution_scope="proof_bounded_scope",
            future_extraction_mode="diagnostic_topn",
            proof_max_future_promotions=proof_max_future_promotions,
            future_query_options=PromotionBaseQueryOptions(
                extraction_mode="diagnostic_topn",
                limit_promotions=proof_max_future_promotions
            ),
            operator_message=(
                "Stage 6 is running in proof-bounded scope. "
                f"Future extraction is limited to top-{proof_max_future_promotions} promotions."
            ),
            planner_verdict="PROOF_BOUNDED_SCOPE",
            proof_bounding_supported_flag=True,
            proof_bounding_reason=(
                "proof_max_future_promotions is enforced via extraction_mode='diagnostic_topn' "
                "with limit_promotions."
            ),
            guardrail_reason=(
                "proof_mode is active and proof_max_future_promotions is set; "
                "future extraction is intentionally bounded for proof survivability."
            ),
            proof_fallback_used=False,
            proof_fallback_mode=None,
            proof_fallback_reason=None,
            query_timeout_seconds=query_timeout_seconds,
        )

    if proof_mode:
        resolved_fallback_mode = proof_future_fallback_mode or "diagnostic_topn"
        if resolved_fallback_mode == "proof_slice":
            fallback_limit = proof_future_fallback_slice_promotions or 25
        else:
            fallback_limit = proof_future_fallback_topn_limit or 50
        return _Stage6ExecutionPlan(
            execution_scope="proof_bounded_scope",
            future_extraction_mode="diagnostic_topn",
            proof_max_future_promotions=fallback_limit,
            future_query_options=PromotionBaseQueryOptions(
                extraction_mode="diagnostic_topn",
                limit_promotions=fallback_limit,
            ),
            operator_message=(
                "Stage 6 proof mode did not receive an explicit future bound; "
                "using governed proof fallback to avoid full-scope future extraction by default."
            ),
            planner_verdict="PROOF_BOUNDED_FALLBACK",
            proof_bounding_supported_flag=True,
            proof_bounding_reason=(
                "proof_mode is enabled with no explicit proof_max_future_promotions; "
                "bounded Stage 6 fallback is applied by policy."
            ),
            guardrail_reason=(
                "proof_mode is active and no explicit Stage 6 future bound was supplied; "
                "future extraction falls back to governed bounded scope."
            ),
            proof_fallback_used=True,
            proof_fallback_mode=resolved_fallback_mode,
            proof_fallback_reason=(
                "Proof mode fallback enforced because no explicit "
                "proof_max_future_promotions was provided. "
                f"Applied {resolved_fallback_mode} with limit_promotions={fallback_limit}."
            ),
            query_timeout_seconds=query_timeout_seconds,
        )

    return _Stage6ExecutionPlan(
        execution_scope="full_scope",
        future_extraction_mode="live_sql",
        proof_max_future_promotions=None,
        future_query_options=None,
        operator_message="Stage 6 is running in normal full-scope live extraction mode.",
        planner_verdict="FULL_SCOPE",
        proof_bounding_supported_flag=False,
        proof_bounding_reason="proof_mode is not enabled.",
        guardrail_reason="proof_mode is not active; full-scope future extraction is required.",
        proof_fallback_used=False,
        proof_fallback_mode=None,
        proof_fallback_reason=None,
        query_timeout_seconds=query_timeout_seconds,
    )


def _serialize_stage6_query_options(
    query_options: PromotionBaseQueryOptions | None,
) -> dict[str, object]:
    """Return a stable JSON-ready representation of Stage 6 query options."""
    if query_options is None:
        return {"extraction_mode": None, "limit_promotions": None}
    return {
        "extraction_mode": query_options.extraction_mode,
        "limit_promotions": query_options.limit_promotions,
        "completed_proof_slice_date_count": query_options.completed_proof_slice_date_count,
    }


def _extract_promotions_base_artifact(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    selection_mode: str,
    progress_callback: Callable[[str], None] | None = None,
    query_options: PromotionBaseQueryOptions | None = None,
) -> PromotionOperationalCycleExtractionArtifacts:
    executor = SqlAlchemyMssqlQueryExecutor.from_settings(settings.sql)
    extraction_result = None
    observability_artifacts = None
    try:
        if _should_use_landed_batch_completed_extraction(
            settings=settings,
            selection_mode=selection_mode,
            query_options=query_options,
        ):
            landed_result = execute_completed_partition_landed_batches(
                settings=settings,
                run_id=run_id,
                executor=executor,
                query_options=query_options,
                progress_callback=progress_callback,
            )
            return PromotionOperationalCycleExtractionArtifacts(
                selection_mode=selection_mode,
                frame=landed_result.frame,
                base_path=landed_result.base_path,
                manifest_path=landed_result.manifest_path,
                rendered_sql_path=landed_result.rendered_sql_path,
                rendered_sql_parameters_path=landed_result.rendered_sql_parameters_path,
                telemetry_json_path=landed_result.telemetry_json_path,
                telemetry_csv_path=landed_result.telemetry_csv_path,
                diagnostics_summary_json_path=landed_result.diagnostics_summary_json_path,
                diagnostics_summary_txt_path=landed_result.diagnostics_summary_txt_path,
                candidate_promotion_row_count=landed_result.candidate_promotion_row_count,
                manifest=landed_result.manifest,
                extraction_mode=landed_result.extraction_mode,
                partition_strategy=landed_result.partition_strategy,
                partition_count=landed_result.partition_count,
                partition_index=landed_result.partition_index,
                fetch_mode=landed_result.fetch_mode,
                chunk_mode=landed_result.chunk_mode,
                chunk_count=landed_result.chunk_count,
                completed_chunk_count=landed_result.completed_chunk_count,
                cumulative_rows_written=landed_result.cumulative_rows_written,
                batch_count=landed_result.batch_count,
                finalized_batch_count=landed_result.finalized_batch_count,
                resumed_batch_count=landed_result.resumed_batch_count,
                rebuilt_batch_count=landed_result.rebuilt_batch_count,
                total_landed_rows=landed_result.total_landed_rows,
                completion_state=landed_result.completion_state,
                partition_completion_state=landed_result.partition_completion_state,
                resume_state=landed_result.resume_state,
                skipped_due_to_existing_completion=(
                    landed_result.skipped_due_to_existing_completion
                ),
                partition_progress_path=landed_result.partition_progress_path,
                partition_completion_marker_path=(
                    landed_result.partition_completion_marker_path
                ),
            )
        extractor = PromotionBaseExtractor(executor=executor)
        if _should_use_chunked_completed_extraction(
            settings=settings,
            selection_mode=selection_mode,
        ):
            chunked_writer = PromotionChunkedExtractionWriter(
                artifact_paths=settings.artifacts,
                run_id=run_id,
                stage_temp_chunk_files=settings.completed_extraction_runtime.stage_temp_chunk_files,
            )
            resume_decision = chunked_writer.resolve_resume_decision(
                resume_completed_partitions=False,
            )
            chunked_writer.start_partition(
                fetch_mode="chunked_fetch",
                chunk_row_count=settings.completed_extraction_runtime.chunk_row_count,
            )
            if progress_callback is not None:
                progress_callback(
                    "chunked fetch enabled | "
                    f"chunk_row_count={settings.completed_extraction_runtime.chunk_row_count} | "
                    f"resume_state={resume_decision.resume_state}"
                )

            def _persist_chunk(frame: pd.DataFrame, chunk_progress) -> None:
                persisted_path = chunked_writer.write_chunk(
                    frame,
                    chunk_index=chunk_progress.chunk_index,
                )
                if progress_callback is not None:
                    progress_callback(
                        "chunk "
                        f"{chunk_progress.chunk_index} | rows {chunk_progress.chunk_row_count} | "
                        f"cumulative_rows {chunk_progress.cumulative_row_count} | "
                        f"persisted {persisted_path if persisted_path is not None else chunked_writer.progress_path}"
                    )

            try:
                extraction_result = extractor.extract_in_chunks(
                    run_id=run_id,
                    settings=settings,
                    selection_mode=selection_mode,
                    chunk_row_count=settings.completed_extraction_runtime.chunk_row_count,
                    chunk_consumer=_persist_chunk,
                    phase_callback=progress_callback,
                    query_options=query_options,
                )
            except Exception as error:
                telemetry = getattr(error, "promotion_extraction_telemetry", None)
                if isinstance(telemetry, PromotionExtractionTelemetry):
                    telemetry.resume_state = resume_decision.resume_state
                    telemetry.partition_completion_state = "failed_incomplete"
                    telemetry.output_partition_progress_path = str(chunked_writer.progress_path)
                    telemetry.output_partition_completion_path = str(
                        chunked_writer.completion_marker_path
                    )
                chunked_writer.mark_failure(failure_message=str(error))
                raise

            if progress_callback is not None:
                progress_callback("fetch complete")
            extraction_result.telemetry.resume_state = resume_decision.resume_state
            extraction_result.telemetry.partition_completion_state = "compacting"
            extraction_result.telemetry.output_partition_progress_path = str(
                chunked_writer.progress_path
            )
            extraction_result.telemetry.output_partition_completion_path = str(
                chunked_writer.completion_marker_path
            )
            extraction_result.telemetry.current_sql_subphase = (
                "compacting chunked parquet and writing manifest"
            )
            extraction_result.telemetry.dataframe_write_started_at_utc = (
                datetime.now(tz=UTC).isoformat()
            )
            finalized_manifest = replace(
                extraction_result.manifest,
                fetch_mode="chunked_fetch",
                chunk_mode="chunked_fetch",
                chunk_count=extraction_result.telemetry.chunk_count,
                completed_chunk_count=extraction_result.telemetry.completed_chunk_count,
                cumulative_rows_written=extraction_result.telemetry.cumulative_rows_written,
                batch_count=1,
                finalized_batch_count=1,
                resumed_batch_count=0,
                rebuilt_batch_count=0,
                total_landed_rows=extraction_result.manifest.row_count,
                completion_state="finalized",
                partition_completion_state="finalized",
                resume_state=resume_decision.resume_state,
                skipped_due_to_existing_completion=False,
            )
            if progress_callback is not None:
                progress_callback("compacting chunked parquet and writing manifest")
            persisted = chunked_writer.finalize(manifest=finalized_manifest)
            extraction_result.telemetry.output_parquet_path = str(persisted.base_path)
            extraction_result.telemetry.output_manifest_path = str(persisted.manifest_path)
            extraction_result.telemetry.output_partition_progress_path = str(
                persisted.progress_path
            )
            extraction_result.telemetry.output_partition_completion_path = str(
                persisted.completion_marker_path
            )
            extraction_result.telemetry.partition_completion_state = (
                persisted.partition_completion_state
            )
            extraction_result.telemetry.resume_state = persisted.resume_state
            extraction_result.telemetry.skipped_due_to_existing_completion = (
                persisted.skipped_due_to_existing_completion
            )
            extraction_result.telemetry.chunk_count = persisted.chunk_count
            extraction_result.telemetry.completed_chunk_count = persisted.completed_chunk_count
            extraction_result.telemetry.cumulative_rows_written = (
                persisted.cumulative_rows_written
            )
            extraction_result.telemetry.dataframe_write_completed_at_utc = (
                datetime.now(tz=UTC).isoformat()
            )
            extraction_result.telemetry.mark_success()
            observability_artifacts = write_extraction_observability(
                telemetry=extraction_result.telemetry,
                settings=settings,
                artifact_paths=settings.artifacts,
            )
            if progress_callback is not None:
                progress_callback("write complete")
            finalized_frame = pd.read_parquet(persisted.base_path)
            return PromotionOperationalCycleExtractionArtifacts(
                selection_mode=selection_mode,
                frame=finalized_frame,
                base_path=str(persisted.base_path),
                manifest_path=str(persisted.manifest_path),
                rendered_sql_path=extraction_result.telemetry.rendered_sql_path,
                rendered_sql_parameters_path=extraction_result.telemetry.rendered_sql_parameters_path,
                telemetry_json_path=observability_artifacts.telemetry_json_path,
                telemetry_csv_path=observability_artifacts.telemetry_csv_path,
                diagnostics_summary_json_path=observability_artifacts.diagnostics_summary_json_path,
                diagnostics_summary_txt_path=observability_artifacts.diagnostics_summary_txt_path,
                candidate_promotion_row_count=extraction_result.telemetry.candidate_promotion_row_count,
                manifest=finalized_manifest.to_dict(),
                extraction_mode=extraction_result.telemetry.extraction_mode,
                partition_strategy=extraction_result.telemetry.partition_strategy,
                partition_count=extraction_result.telemetry.partition_count,
                partition_index=extraction_result.telemetry.partition_index,
                fetch_mode=extraction_result.telemetry.fetch_mode,
                chunk_mode=finalized_manifest.chunk_mode,
                chunk_count=persisted.chunk_count,
                completed_chunk_count=persisted.completed_chunk_count,
                cumulative_rows_written=persisted.cumulative_rows_written,
                batch_count=finalized_manifest.batch_count,
                finalized_batch_count=finalized_manifest.finalized_batch_count,
                resumed_batch_count=finalized_manifest.resumed_batch_count,
                rebuilt_batch_count=finalized_manifest.rebuilt_batch_count,
                total_landed_rows=finalized_manifest.total_landed_rows,
                completion_state=finalized_manifest.completion_state,
                partition_completion_state=persisted.partition_completion_state,
                resume_state=persisted.resume_state,
                skipped_due_to_existing_completion=(
                    persisted.skipped_due_to_existing_completion
                ),
                partition_progress_path=str(persisted.progress_path),
                partition_completion_marker_path=str(persisted.completion_marker_path),
            )

        extraction_result = extractor.extract(
            run_id=run_id,
            settings=settings,
            selection_mode=selection_mode,
            phase_callback=progress_callback,
            query_options=query_options,
        )
        if progress_callback is not None:
            progress_callback("fetch complete")
        extraction_result.telemetry.current_sql_subphase = "writing extracted parquet and manifest"
        extraction_result.telemetry.dataframe_write_started_at_utc = datetime.now(tz=UTC).isoformat()
        if progress_callback is not None:
            progress_callback("writing extracted parquet and manifest")
        finalized_manifest = replace(
            extraction_result.manifest,
            chunk_mode=extraction_result.telemetry.chunk_mode,
            batch_count=1,
            finalized_batch_count=1,
            resumed_batch_count=0,
            rebuilt_batch_count=0,
            total_landed_rows=extraction_result.manifest.row_count,
            completion_state="finalized",
            partition_completion_state="finalized",
            resume_state=extraction_result.telemetry.resume_state,
            skipped_due_to_existing_completion=False,
        )
        persisted = PromotionExtractionWriter().write(
            base_frame=extraction_result.base_frame,
            manifest=finalized_manifest,
            artifact_paths=settings.artifacts,
        )
        extraction_result.telemetry.output_parquet_path = str(persisted.base_path)
        extraction_result.telemetry.output_manifest_path = str(persisted.manifest_path)
        extraction_result.telemetry.chunk_mode = finalized_manifest.chunk_mode
        extraction_result.telemetry.batch_count = finalized_manifest.batch_count
        extraction_result.telemetry.finalized_batch_count = finalized_manifest.finalized_batch_count
        extraction_result.telemetry.resumed_batch_count = finalized_manifest.resumed_batch_count
        extraction_result.telemetry.rebuilt_batch_count = finalized_manifest.rebuilt_batch_count
        extraction_result.telemetry.total_landed_rows = finalized_manifest.total_landed_rows
        extraction_result.telemetry.completion_state = finalized_manifest.completion_state
        extraction_result.telemetry.partition_completion_state = finalized_manifest.partition_completion_state
        extraction_result.telemetry.dataframe_write_completed_at_utc = datetime.now(tz=UTC).isoformat()
        extraction_result.telemetry.mark_success()
        observability_artifacts = write_extraction_observability(
            telemetry=extraction_result.telemetry,
            settings=settings,
            artifact_paths=settings.artifacts,
        )
        if progress_callback is not None:
            progress_callback("write complete")
        return PromotionOperationalCycleExtractionArtifacts(
            selection_mode=selection_mode,
            frame=extraction_result.base_frame,
            base_path=str(persisted.base_path),
            manifest_path=str(persisted.manifest_path),
            rendered_sql_path=extraction_result.telemetry.rendered_sql_path,
            rendered_sql_parameters_path=extraction_result.telemetry.rendered_sql_parameters_path,
            telemetry_json_path=observability_artifacts.telemetry_json_path,
            telemetry_csv_path=observability_artifacts.telemetry_csv_path,
            diagnostics_summary_json_path=observability_artifacts.diagnostics_summary_json_path,
            diagnostics_summary_txt_path=observability_artifacts.diagnostics_summary_txt_path,
            candidate_promotion_row_count=extraction_result.telemetry.candidate_promotion_row_count,
            manifest=finalized_manifest.to_dict(),
            extraction_mode=extraction_result.telemetry.extraction_mode,
            partition_strategy=extraction_result.telemetry.partition_strategy,
            partition_count=extraction_result.telemetry.partition_count,
            partition_index=extraction_result.telemetry.partition_index,
            fetch_mode=extraction_result.telemetry.fetch_mode,
            chunk_mode=finalized_manifest.chunk_mode,
            chunk_count=extraction_result.telemetry.chunk_count,
            completed_chunk_count=extraction_result.telemetry.completed_chunk_count,
            cumulative_rows_written=extraction_result.telemetry.cumulative_rows_written,
            batch_count=finalized_manifest.batch_count,
            finalized_batch_count=finalized_manifest.finalized_batch_count,
            resumed_batch_count=finalized_manifest.resumed_batch_count,
            rebuilt_batch_count=finalized_manifest.rebuilt_batch_count,
            total_landed_rows=finalized_manifest.total_landed_rows,
            completion_state=finalized_manifest.completion_state,
            partition_completion_state=extraction_result.telemetry.partition_completion_state,
            resume_state=extraction_result.telemetry.resume_state,
            skipped_due_to_existing_completion=(
                extraction_result.telemetry.skipped_due_to_existing_completion
            ),
            partition_progress_path=extraction_result.telemetry.output_partition_progress_path,
            partition_completion_marker_path=(
                extraction_result.telemetry.output_partition_completion_path
            ),
        )
    except Exception as error:
        telemetry = _resolve_failed_extraction_telemetry(
            error=error,
            extraction_result=extraction_result,
            settings=settings,
            run_id=run_id,
            selection_mode=selection_mode,
        )
        if telemetry is not None:
            observability_artifacts = write_extraction_observability(
                telemetry=telemetry,
                settings=settings,
                artifact_paths=settings.artifacts,
            )
            _attach_extraction_failure_context(error, observability_artifacts, telemetry)
        raise


def _completed_stage_message(
    *,
    partition_settings: PromotionCompletedPartitionSettings | None,
    execution_mode: str,
) -> str:
    if partition_settings is None:
        return _stage_subtask_message("completed", execution_mode)
    return (
        "preparing partitioned SQL extraction for completed promotions "
        f"using {partition_settings.strategy} across {partition_settings.partition_count} partitions"
    )


def _partition_strategy_label(
    partition_settings: PromotionCompletedPartitionSettings | None,
) -> str:
    if partition_settings is None:
        return FULL_COMPLETED_SCOPE_STRATEGY
    return partition_settings.strategy


def _partition_strategy_value(
    partition_settings: PromotionCompletedPartitionSettings | None,
) -> str | None:
    if partition_settings is None:
        return None
    return partition_settings.strategy


def _partition_count_value(
    partition_settings: PromotionCompletedPartitionSettings | None,
) -> int | None:
    if partition_settings is None:
        return None
    return partition_settings.partition_count


def _partition_count_label(
    partition_settings: PromotionCompletedPartitionSettings | None,
) -> str:
    if partition_settings is None:
        return "full_scope"
    return str(partition_settings.partition_count)


def _accepted_completed_repartition_attempt_count(
    retry_records: list[PromotionCompletedPartitionRetryRecord],
) -> int:
    return sum(1 for record in retry_records if record.status == "accepted")


def _attach_completed_partition_retry_context(
    *,
    error: BaseException,
    retry_records: list[PromotionCompletedPartitionRetryRecord],
    retry_json_path: str,
    retry_csv_path: str,
    planner_settings: PromotionCompletedPreflightPlannerSettings,
) -> None:
    setattr(error, "completed_partition_retries_json_path", retry_json_path)
    setattr(error, "completed_partition_retries_csv_path", retry_csv_path)
    setattr(
        error,
        "completed_repartition_attempts_tried",
        _accepted_completed_repartition_attempt_count(retry_records),
    )
    setattr(
        error,
        "max_completed_repartition_attempts",
        planner_settings.max_completed_repartition_attempts,
    )
    setattr(
        error,
        "max_completed_partition_count",
        planner_settings.max_completed_partition_count,
    )


def _resolve_completed_repartition_retry(
    *,
    run_id: str,
    current_partition_settings: PromotionCompletedPartitionSettings | None,
    error: PromotionCompletedPreflightRejectedError,
    planner_settings: PromotionCompletedPreflightPlannerSettings,
    attempt_number: int,
) -> tuple[
    PromotionCompletedPartitionSettings | None,
    PromotionCompletedPartitionRetryRecord,
    str,
]:
    initial_partition_strategy = _partition_strategy_label(current_partition_settings)
    initial_partition_count = _partition_count_value(current_partition_settings)
    recommended_partition_strategy = getattr(error, "recommended_partition_strategy", None)
    recommended_partition_count = getattr(error, "recommended_partition_count", None)
    verdict = getattr(error, "preflight_verdict", None) or "unavailable"
    reason = getattr(error, "preflight_reason", None) or str(error)
    failed_partition_index = getattr(error, "partition_index", None)
    current_partition_count_floor = initial_partition_count if initial_partition_count is not None else 1
    next_partition_settings: PromotionCompletedPartitionSettings | None = None
    status = "accepted"
    decision_reason = ""

    if not planner_settings.auto_repartition_completed:
        status = "rejected_auto_repartition_disabled"
        decision_reason = (
            "automatic completed repartition is disabled for this run, so the live operator cannot accept the planner recommendation automatically."
        )
    elif verdict != "TOO_WIDE_REPARTITION_REQUIRED":
        status = "rejected_non_repartition_verdict"
        decision_reason = (
            f"preflight verdict {verdict} is not eligible for automatic repartition retry."
        )
    elif recommended_partition_strategy not in VALID_COMPLETED_PARTITION_STRATEGIES:
        status = "rejected_invalid_strategy"
        decision_reason = (
            "the planner recommendation did not include a valid governed partition strategy for automatic retry."
        )
    elif recommended_partition_count is None or recommended_partition_count < 1:
        status = "rejected_invalid_partition_count"
        decision_reason = (
            "the planner recommendation did not include a usable partition_count for automatic retry."
        )
    elif recommended_partition_count <= current_partition_count_floor:
        status = "rejected_non_increasing_partition_count"
        decision_reason = (
            f"recommended partition_count {recommended_partition_count} is not greater than the current completed partition_count {current_partition_count_floor}."
        )
    elif attempt_number > planner_settings.max_completed_repartition_attempts:
        status = "rejected_max_attempts"
        decision_reason = (
            "completed promotions preflight remained unsafe after "
            f"{planner_settings.max_completed_repartition_attempts} repartition attempts; "
            f"last recommendation was {recommended_partition_strategy} with partition_count {recommended_partition_count}."
        )
    elif recommended_partition_count > planner_settings.max_completed_partition_count:
        status = "rejected_max_partition_count"
        decision_reason = (
            f"recommended partition_count {recommended_partition_count} exceeds the governed max_completed_partition_count {planner_settings.max_completed_partition_count}."
        )
    else:
        next_partition_settings = PromotionCompletedPartitionSettings(
            strategy=recommended_partition_strategy,
            partition_count=recommended_partition_count,
        )
        decision_reason = (
            f"accepted automatic repartition retry {attempt_number}/"
            f"{planner_settings.max_completed_repartition_attempts}: "
            f"{initial_partition_strategy}/{initial_partition_count if initial_partition_count is not None else 'full_scope'} "
            f"-> {recommended_partition_strategy}/{recommended_partition_count}."
        )

    retry_record = PromotionCompletedPartitionRetryRecord(
        run_id=run_id,
        stage=COMPLETED_EXTRACTION_STAGE_NAME,
        attempt_number=attempt_number,
        selection_mode="completed",
        initial_partition_strategy=initial_partition_strategy,
        initial_partition_count=initial_partition_count,
        recommended_partition_strategy=recommended_partition_strategy,
        recommended_partition_count=recommended_partition_count,
        accepted_strategy=(next_partition_settings.strategy if next_partition_settings is not None else None),
        accepted_partition_count=(
            next_partition_settings.partition_count if next_partition_settings is not None else None
        ),
        verdict=verdict,
        reason=reason,
        failed_partition_index=failed_partition_index,
        candidate_promotion_row_count=getattr(error, "candidate_promotion_row_count", None),
        candidate_store_sku_count=getattr(error, "candidate_store_sku_count", None),
        candidate_window_count=getattr(error, "candidate_window_count", None),
        candidate_window_span_days_total=getattr(error, "candidate_window_span_days_total", None),
        candidate_window_span_days_max=getattr(error, "candidate_window_span_days_max", None),
        estimated_cost_score=getattr(error, "estimated_cost_score", None),
        cost_guardrail_verdict=getattr(error, "cost_guardrail_verdict", None),
        cost_guardrail_reason=getattr(error, "cost_guardrail_reason", None),
        status=status,
    )
    return next_partition_settings, retry_record, decision_reason


def _write_completed_partition_retry_history(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    requested_partition_settings: PromotionCompletedPartitionSettings | None,
    active_partition_settings: PromotionCompletedPartitionSettings | None,
    retry_records: list[PromotionCompletedPartitionRetryRecord],
    planner_settings: PromotionCompletedPreflightPlannerSettings,
) -> tuple[str, str]:
    json_path = settings.artifacts.completed_partition_retries_json_path(run_id)
    csv_path = settings.artifacts.completed_partition_retries_csv_path(run_id)
    fieldnames = (
        "run_id",
        "stage",
        "attempt_number",
        "selection_mode",
        "initial_partition_strategy",
        "initial_partition_count",
        "recommended_partition_strategy",
        "recommended_partition_count",
        "accepted_strategy",
        "accepted_partition_count",
        "verdict",
        "reason",
        "failed_partition_index",
        "candidate_promotion_row_count",
        "candidate_store_sku_count",
        "candidate_window_count",
        "candidate_window_span_days_total",
        "candidate_window_span_days_max",
        "estimated_cost_score",
        "cost_guardrail_verdict",
        "cost_guardrail_reason",
        "status",
    )
    payload = {
        "run_id": run_id,
        "stage": COMPLETED_EXTRACTION_STAGE_NAME,
        "selection_mode": "completed",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "requested_partition_strategy": _partition_strategy_label(requested_partition_settings),
        "requested_partition_count": _partition_count_value(requested_partition_settings),
        "active_partition_strategy": _partition_strategy_label(active_partition_settings),
        "active_partition_count": _partition_count_value(active_partition_settings),
        "auto_repartition_completed": planner_settings.auto_repartition_completed,
        "max_completed_repartition_attempts": planner_settings.max_completed_repartition_attempts,
        "max_completed_partition_count": planner_settings.max_completed_partition_count,
        "retry_event_count": len(retry_records),
        "accepted_retry_count": _accepted_completed_repartition_attempt_count(retry_records),
        "attempts": [record.to_dict() for record in retry_records],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in retry_records:
            writer.writerow(record.to_dict())
    return str(json_path), str(csv_path)


def _write_completed_preflight_rejection_summary(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    error: BaseException,
) -> str:
    summary_path = settings.artifacts.completed_partition_summary_path(run_id)
    partition_strategy = getattr(error, "partition_strategy", None)
    payload = {
        "run_id": run_id,
        "selection_mode": "completed",
        "partition_strategy": partition_strategy or FULL_COMPLETED_SCOPE_STRATEGY,
        "partition_count": getattr(error, "partition_count", None),
        "partitions_succeeded": 0,
        "partitions_failed": 1,
        "total_candidate_promotion_row_count": getattr(
            error,
            "candidate_promotion_row_count",
            None,
        ),
        "total_extracted_row_count": 0,
        "combined_base_path": None,
        "combined_manifest_path": None,
        "partitions": [
            {
                "partition_strategy": partition_strategy or FULL_COMPLETED_SCOPE_STRATEGY,
                "partition_count": getattr(error, "partition_count", None),
                "partition_index": getattr(error, "partition_index", None),
                "partition_label": (
                    f"partition {getattr(error, 'partition_index', None)}/{getattr(error, 'partition_count', None)}"
                    if getattr(error, "partition_index", None) is not None
                    and getattr(error, "partition_count", None) is not None
                    else "full completed scope"
                ),
                "run_id": run_id,
                "extraction_status": "preflight_rejected",
                "preflight_verdict": getattr(error, "preflight_verdict", None),
                "preflight_reason": getattr(error, "preflight_reason", None),
                "recommended_partition_strategy": getattr(
                    error,
                    "recommended_partition_strategy",
                    None,
                ),
                "recommended_partition_count": getattr(
                    error,
                    "recommended_partition_count",
                    None,
                ),
                "estimated_cost_score": getattr(error, "estimated_cost_score", None),
                "estimated_extract_query_seconds": getattr(
                    error,
                    "estimated_extract_query_seconds",
                    None,
                ),
                "fixed_overhead_seconds": getattr(error, "fixed_overhead_seconds", None),
                "variable_cost_signal": getattr(error, "variable_cost_signal", None),
                "cost_model_version": getattr(error, "cost_model_version", None),
                "candidate_promotion_row_count": getattr(
                    error,
                    "candidate_promotion_row_count",
                    None,
                ),
                "candidate_store_sku_count": getattr(error, "candidate_store_sku_count", None),
                "candidate_window_count": getattr(error, "candidate_window_count", None),
                "candidate_window_span_days_total": getattr(
                    error,
                    "candidate_window_span_days_total",
                    None,
                ),
                "candidate_window_span_days_max": getattr(
                    error,
                    "candidate_window_span_days_max",
                    None,
                ),
                "final_extracted_row_count": 0,
                "phase_elapsed_seconds": None,
                "total_elapsed_seconds": None,
                "preflight_summary_json_path": getattr(error, "preflight_summary_json_path", None),
                "preflight_summary_csv_path": getattr(error, "preflight_summary_csv_path", None),
                "rendered_preflight_sql_path": getattr(error, "rendered_preflight_sql_path", None),
                "rendered_preflight_sql_parameters_path": getattr(
                    error,
                    "rendered_preflight_sql_parameters_path",
                    None,
                ),
                "completed_preflight_cost_diagnostic_path": getattr(
                    error,
                    "completed_preflight_cost_diagnostic_path",
                    None,
                ),
                "proof_fallback_used": getattr(error, "completed_proof_fallback_used", False),
                "proof_fallback_mode": getattr(error, "completed_proof_fallback_mode", None),
                "proof_fallback_reason": getattr(error, "completed_proof_fallback_reason", None),
                "base_path": None,
                "manifest_path": None,
                "rendered_sql_path": getattr(error, "rendered_sql_path", None),
                "rendered_sql_parameters_path": getattr(error, "rendered_sql_parameters_path", None),
                "telemetry_json_path": getattr(error, "extraction_telemetry_json_path", None),
                "telemetry_csv_path": getattr(error, "extraction_telemetry_csv_path", None),
                "sql_diagnostics_summary_json_path": getattr(
                    error,
                    "sql_diagnostics_summary_json_path",
                    None,
                ),
                "sql_diagnostics_summary_txt_path": getattr(
                    error,
                    "sql_diagnostics_summary_txt_path",
                    None,
                ),
                "failure_exception_type": type(error).__name__,
                "failure_message": str(error),
            }
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(summary_path)


def _coerce_optional_int(value: object | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _coerce_optional_float(value: object | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_existing_path(path: Path) -> str | None:
    return str(path) if path.exists() else None


def _compute_promotion_row_key_checksum(frame: pd.DataFrame) -> str | None:
    if "promotion_row_key" not in frame.columns:
        return None
    digest = __import__("hashlib").sha256()
    for row_key in frame["promotion_row_key"].tolist():
        digest.update(str(row_key).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _load_existing_completed_partition_artifact(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    partition_settings: PromotionCompletedPartitionSettings,
) -> PromotionOperationalCycleExtractionArtifacts:
    progress_path = settings.artifacts.extraction_partition_progress_path(run_id)
    preflight_summary_json_path = settings.artifacts.extraction_preflight_summary_json_path(run_id)
    preflight_summary_csv_path = settings.artifacts.extraction_preflight_summary_csv_path(run_id)
    rendered_preflight_sql_path = settings.artifacts.rendered_preflight_sql_path(run_id)
    rendered_preflight_sql_parameters_path = settings.artifacts.rendered_preflight_sql_parameters_path(
        run_id
    )

    resolved_partition = load_existing_finalized_partition_artifact(
        settings=settings,
        run_id=run_id,
        query_options=PromotionBaseQueryOptions(completed_partition=partition_settings),
    )
    if resolved_partition is None:
        resolved_chunked_partition = _load_existing_chunked_partition_artifact(
            settings=settings,
            run_id=run_id,
            partition_settings=partition_settings,
            progress_path=progress_path,
            preflight_summary_json_path=preflight_summary_json_path,
            preflight_summary_csv_path=preflight_summary_csv_path,
            rendered_preflight_sql_path=rendered_preflight_sql_path,
            rendered_preflight_sql_parameters_path=rendered_preflight_sql_parameters_path,
        )
        if resolved_chunked_partition is not None:
            return resolved_chunked_partition
        raise PromotionInvalidResumeStateError(
            "Completed partition resume requested but no finalized reusable partition artifact could be resolved."
        )
    preflight_payload = _read_optional_json(str(preflight_summary_json_path))
    return PromotionOperationalCycleExtractionArtifacts(
        selection_mode="completed",
        frame=resolved_partition.frame,
        base_path=resolved_partition.base_path,
        manifest_path=resolved_partition.manifest_path,
        rendered_sql_path=resolved_partition.rendered_sql_path,
        rendered_sql_parameters_path=resolved_partition.rendered_sql_parameters_path,
        telemetry_json_path=resolved_partition.telemetry_json_path,
        telemetry_csv_path=resolved_partition.telemetry_csv_path,
        diagnostics_summary_json_path=resolved_partition.diagnostics_summary_json_path,
        diagnostics_summary_txt_path=resolved_partition.diagnostics_summary_txt_path,
        candidate_promotion_row_count=resolved_partition.candidate_promotion_row_count,
        manifest=resolved_partition.manifest,
        extraction_mode=resolved_partition.extraction_mode,
        partition_strategy=resolved_partition.partition_strategy,
        partition_count=resolved_partition.partition_count,
        partition_index=resolved_partition.partition_index,
        fetch_mode=resolved_partition.fetch_mode,
        chunk_mode=resolved_partition.chunk_mode,
        chunk_count=resolved_partition.chunk_count,
        completed_chunk_count=resolved_partition.completed_chunk_count,
        cumulative_rows_written=resolved_partition.cumulative_rows_written,
        batch_count=resolved_partition.batch_count,
        finalized_batch_count=resolved_partition.finalized_batch_count,
        resumed_batch_count=resolved_partition.resumed_batch_count,
        rebuilt_batch_count=resolved_partition.rebuilt_batch_count,
        total_landed_rows=resolved_partition.total_landed_rows,
        completion_state=resolved_partition.completion_state,
        partition_completion_state=resolved_partition.partition_completion_state,
        resume_state=resolved_partition.resume_state,
        skipped_due_to_existing_completion=resolved_partition.skipped_due_to_existing_completion,
        partition_progress_path=_optional_existing_path(progress_path),
        partition_completion_marker_path=resolved_partition.partition_completion_marker_path,
        preflight_summary_json_path=_optional_existing_path(preflight_summary_json_path),
        preflight_summary_csv_path=_optional_existing_path(preflight_summary_csv_path),
        rendered_preflight_sql_path=_optional_existing_path(rendered_preflight_sql_path),
        rendered_preflight_sql_parameters_path=_optional_existing_path(
            rendered_preflight_sql_parameters_path
        ),
        preflight_verdict=(
            preflight_payload.get("verdict") if preflight_payload.get("verdict") is not None else None
        ),
        preflight_reason=(
            preflight_payload.get("reason") if preflight_payload.get("reason") is not None else None
        ),
        estimated_cost_score=_coerce_optional_float(preflight_payload.get("estimated_cost_score")),
        cost_guardrail_verdict=(
            preflight_payload.get("cost_guardrail_verdict")
            if preflight_payload.get("cost_guardrail_verdict") is not None
            else None
        ),
        cost_guardrail_reason=(
            preflight_payload.get("cost_guardrail_reason")
            if preflight_payload.get("cost_guardrail_reason") is not None
            else None
        ),
        recommended_partition_strategy=(
            preflight_payload.get("recommended_partition_strategy")
            if preflight_payload.get("recommended_partition_strategy") is not None
            else None
        ),
        recommended_partition_count=_coerce_optional_int(
            preflight_payload.get("recommended_partition_count")
        ),
    )


def _load_existing_chunked_partition_artifact(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    partition_settings: PromotionCompletedPartitionSettings,
    progress_path: Path,
    preflight_summary_json_path: Path,
    preflight_summary_csv_path: Path,
    rendered_preflight_sql_path: Path,
    rendered_preflight_sql_parameters_path: Path,
) -> PromotionOperationalCycleExtractionArtifacts | None:
    completion_path = settings.artifacts.extraction_partition_completion_path(run_id)
    if not completion_path.exists():
        return None
    completion_payload = _read_optional_json(str(completion_path))
    if completion_payload.get("partition_completion_state") != "finalized":
        return None

    base_path = settings.artifacts.extracted_base_path(run_id)
    manifest_path = settings.artifacts.extracted_manifest_path(run_id)
    if not base_path.exists() or not manifest_path.exists():
        raise PromotionInvalidResumeStateError(
            "Completion marker is finalized but the completed partition parquet or manifest is missing."
        )

    manifest_payload = _read_optional_json(str(manifest_path))
    if not manifest_payload:
        raise PromotionInvalidResumeStateError(
            "Completion marker is finalized but the completed partition manifest could not be parsed."
        )

    fetch_mode = str(
        manifest_payload.get("fetch_mode")
        or completion_payload.get("fetch_mode")
        or ""
    )
    if fetch_mode == "landed_batch_fetch":
        return None
    if fetch_mode not in {"chunked_fetch", "full_fetch"}:
        raise PromotionInvalidResumeStateError(
            f"Unsupported finalized partition fetch_mode '{fetch_mode}' for resumed completed extraction."
        )

    try:
        frame = pd.read_parquet(base_path)
    except Exception as error:
        raise PromotionInvalidResumeStateError(
            "Finalized completed partition parquet could not be read during resume."
        ) from error

    preflight_payload = _read_optional_json(str(preflight_summary_json_path))
    return PromotionOperationalCycleExtractionArtifacts(
        selection_mode="completed",
        frame=frame,
        base_path=str(base_path),
        manifest_path=str(manifest_path),
        rendered_sql_path=_optional_existing_path(
            settings.artifacts.manifests_run_root(run_id) / "rendered_sql.sql"
        ),
        rendered_sql_parameters_path=_optional_existing_path(
            settings.artifacts.manifests_run_root(run_id) / "rendered_sql_parameters.json"
        ),
        telemetry_json_path=_optional_existing_path(settings.artifacts.extraction_telemetry_json_path(run_id)),
        telemetry_csv_path=_optional_existing_path(settings.artifacts.extraction_telemetry_csv_path(run_id)),
        diagnostics_summary_json_path=_optional_existing_path(
            settings.artifacts.sql_diagnostics_summary_json_path(run_id)
        ),
        diagnostics_summary_txt_path=_optional_existing_path(
            settings.artifacts.sql_diagnostics_summary_txt_path(run_id)
        ),
        candidate_promotion_row_count=_coerce_optional_int(
            manifest_payload.get("candidate_promotion_row_count")
        ),
        manifest=manifest_payload,
        extraction_mode=str(manifest_payload.get("extraction_mode", "live_sql")),
        partition_strategy=partition_settings.strategy,
        partition_count=partition_settings.partition_count,
        partition_index=partition_settings.partition_index,
        fetch_mode=fetch_mode,
        chunk_mode=str(
            manifest_payload.get("chunk_mode")
            or completion_payload.get("chunk_mode")
            or "full_fetch"
        ),
        chunk_count=_coerce_optional_int(completion_payload.get("chunk_count")) or 0,
        completed_chunk_count=_coerce_optional_int(completion_payload.get("completed_chunk_count")) or 0,
        cumulative_rows_written=_coerce_optional_int(
            completion_payload.get("cumulative_rows_written")
        ) or int(len(frame.index)),
        batch_count=_coerce_optional_int(manifest_payload.get("batch_count")) or 0,
        finalized_batch_count=_coerce_optional_int(manifest_payload.get("finalized_batch_count")) or 0,
        resumed_batch_count=_coerce_optional_int(manifest_payload.get("resumed_batch_count")) or 0,
        rebuilt_batch_count=_coerce_optional_int(manifest_payload.get("rebuilt_batch_count")) or 0,
        total_landed_rows=_coerce_optional_int(manifest_payload.get("total_landed_rows")) or 0,
        completion_state=(
            str(manifest_payload.get("completion_state"))
            if manifest_payload.get("completion_state") is not None
            else None
        ),
        partition_completion_state=(
            str(completion_payload.get("partition_completion_state"))
            if completion_payload.get("partition_completion_state") is not None
            else None
        ),
        resume_state=(
            str(completion_payload.get("resume_state"))
            if completion_payload.get("resume_state") is not None
            else None
        ),
        skipped_due_to_existing_completion=bool(
            completion_payload.get("skipped_due_to_existing_completion", True)
        ),
        partition_progress_path=_optional_existing_path(progress_path),
        partition_completion_marker_path=str(completion_path),
        preflight_summary_json_path=_optional_existing_path(preflight_summary_json_path),
        preflight_summary_csv_path=_optional_existing_path(preflight_summary_csv_path),
        rendered_preflight_sql_path=_optional_existing_path(rendered_preflight_sql_path),
        rendered_preflight_sql_parameters_path=_optional_existing_path(
            rendered_preflight_sql_parameters_path
        ),
        preflight_verdict=(
            preflight_payload.get("verdict")
            if preflight_payload.get("verdict") is not None
            else None
        ),
        preflight_reason=(
            preflight_payload.get("reason")
            if preflight_payload.get("reason") is not None
            else None
        ),
        estimated_cost_score=_coerce_optional_float(preflight_payload.get("estimated_cost_score")),
        cost_guardrail_verdict=(
            preflight_payload.get("cost_guardrail_verdict")
            if preflight_payload.get("cost_guardrail_verdict") is not None
            else None
        ),
        cost_guardrail_reason=(
            preflight_payload.get("cost_guardrail_reason")
            if preflight_payload.get("cost_guardrail_reason") is not None
            else None
        ),
        recommended_partition_strategy=(
            preflight_payload.get("recommended_partition_strategy")
            if preflight_payload.get("recommended_partition_strategy") is not None
            else None
        ),
        recommended_partition_count=_coerce_optional_int(
            preflight_payload.get("recommended_partition_count")
        ),
    )


def _extract_completed_promotions_partitioned_artifact(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    partition_settings: PromotionCompletedPartitionSettings,
    extraction_runner: Callable[..., PromotionOperationalCycleExtractionArtifacts],
    progress: PromotionOperatorProgress,
    run_preflight: bool,
) -> PromotionOperationalCycleExtractionArtifacts:
    partition_entries: list[dict[str, object]] = []
    partition_artifacts: list[PromotionOperationalCycleExtractionArtifacts] = []
    active_partition: PromotionCompletedPartitionSettings | None = None
    try:
        for partition_index in range(1, partition_settings.partition_count + 1):
            active_partition = partition_settings.with_partition_index(partition_index)
            partition_run_id = _completed_partition_run_id(run_id, active_partition)
            resume_probe = None
            progress.detail(
                f"partition_run_id[{partition_index}/{partition_settings.partition_count}]: {partition_run_id}"
            )
            if _should_use_chunked_completed_extraction(
                settings=settings,
                selection_mode="completed",
            ):
                resume_probe = PromotionChunkedExtractionWriter(
                    artifact_paths=settings.artifacts,
                    run_id=partition_run_id,
                    stage_temp_chunk_files=(
                        settings.completed_extraction_runtime.stage_temp_chunk_files
                    ),
                ).resolve_resume_decision(
                    resume_completed_partitions=(
                        settings.completed_extraction_runtime.resume_completed_partitions
                    )
                )
                progress.detail(
                    "partition_resume_state"
                    f"[{partition_index}/{partition_settings.partition_count}]: {resume_probe.resume_state}"
                )
                if resume_probe.skipped_due_to_existing_completion:
                    progress.update_heartbeat(
                        subtask=(
                            f"{_completed_partition_label(active_partition)} | "
                            "reusing finalized partition artifact"
                        ),
                        emit_now=True,
                    )
                    partition_artifact = _load_existing_completed_partition_artifact(
                        settings=settings,
                        run_id=partition_run_id,
                        partition_settings=active_partition,
                    )
                    partition_artifact = replace(
                        partition_artifact,
                        resume_state="skip_finalized_partition",
                        skipped_due_to_existing_completion=True,
                    )
                    partition_artifacts.append(partition_artifact)
                    partition_entries.append(
                        _build_completed_partition_summary_entry_from_artifact(
                            partition_settings=active_partition,
                            partition_run_id=partition_run_id,
                            extraction_artifact=partition_artifact,
                            preflight_result=None,
                        )
                    )
                    progress.detail(
                        f"candidate_rows[{partition_index}/{partition_settings.partition_count}]: {partition_artifact.candidate_promotion_row_count or 0}"
                    )
                    progress.detail(
                        "extracted_rows"
                        f"[{partition_index}/{partition_settings.partition_count}]: {int(partition_artifact.manifest.get('row_count', 0) or 0)}"
                    )
                    continue
            preflight_result: PromotionExtractionPreflightResult | None = None
            if run_preflight:
                progress.update_heartbeat(
                    subtask=f"{_completed_partition_label(active_partition)} | preflight transaction-scope probe",
                    emit_now=True,
                )
                preflight_result = _run_completed_preflight_probe(
                    settings=settings,
                    run_id=partition_run_id,
                    query_options=PromotionBaseQueryOptions(completed_partition=active_partition),
                )
                _emit_completed_preflight_summary(
                    progress=progress,
                    preflight_result=preflight_result,
                    partition_label=_completed_partition_label(active_partition),
                )
                if preflight_result.summary.verdict != "SAFE_TO_EXTRACT":
                    _raise_for_completed_preflight_verdict(
                        preflight_result=preflight_result,
                        selection_mode="completed",
                        as_of_date=settings.as_of_date.isoformat(),
                    )
            partition_artifact = extraction_runner(
                settings=settings,
                run_id=partition_run_id,
                selection_mode="completed",
                progress_callback=lambda subtask, current=active_partition: progress.update_heartbeat(
                    subtask=f"{_completed_partition_label(current)} | {subtask}",
                    emit_now=True,
                ),
                query_options=PromotionBaseQueryOptions(completed_partition=active_partition),
            )
            if resume_probe is not None:
                partition_artifact = replace(
                    partition_artifact,
                    resume_state=resume_probe.resume_state,
                    skipped_due_to_existing_completion=False,
                    partition_progress_path=(
                        partition_artifact.partition_progress_path
                        or _optional_existing_path(
                            settings.artifacts.extraction_partition_progress_path(partition_run_id)
                        )
                    ),
                    partition_completion_marker_path=(
                        partition_artifact.partition_completion_marker_path
                        or _optional_existing_path(
                            settings.artifacts.extraction_partition_completion_path(
                                partition_run_id
                            )
                        )
                    ),
                )
            if preflight_result is not None:
                partition_artifact = _with_preflight_artifacts(
                    extraction_artifact=partition_artifact,
                    preflight_result=preflight_result,
                )
            partition_artifacts.append(partition_artifact)
            partition_entries.append(
                _build_completed_partition_summary_entry_from_artifact(
                    partition_settings=active_partition,
                    partition_run_id=partition_run_id,
                    extraction_artifact=partition_artifact,
                    preflight_result=preflight_result,
                )
            )
            progress.detail(
                f"candidate_rows[{partition_index}/{partition_settings.partition_count}]: {partition_artifact.candidate_promotion_row_count or 0}"
            )
            progress.detail(
                "extracted_rows"
                f"[{partition_index}/{partition_settings.partition_count}]: {int(partition_artifact.manifest.get('row_count', 0) or 0)}"
            )
        combined_artifact = _combine_completed_partition_artifacts(
            settings=settings,
            run_id=run_id,
            partition_settings=partition_settings,
            partition_artifacts=partition_artifacts,
        )
        partition_summary_path = _write_completed_partition_summary(
            settings=settings,
            run_id=run_id,
            partition_settings=partition_settings,
            partition_entries=partition_entries,
            combined_artifact=combined_artifact,
        )
        return PromotionOperationalCycleExtractionArtifacts(
            selection_mode=combined_artifact.selection_mode,
            frame=combined_artifact.frame,
            base_path=combined_artifact.base_path,
            manifest_path=combined_artifact.manifest_path,
            rendered_sql_path=combined_artifact.rendered_sql_path,
            rendered_sql_parameters_path=combined_artifact.rendered_sql_parameters_path,
            telemetry_json_path=combined_artifact.telemetry_json_path,
            telemetry_csv_path=combined_artifact.telemetry_csv_path,
            diagnostics_summary_json_path=combined_artifact.diagnostics_summary_json_path,
            diagnostics_summary_txt_path=combined_artifact.diagnostics_summary_txt_path,
            candidate_promotion_row_count=combined_artifact.candidate_promotion_row_count,
            manifest=combined_artifact.manifest,
            extraction_mode=combined_artifact.extraction_mode,
            partition_strategy=combined_artifact.partition_strategy,
            partition_count=combined_artifact.partition_count,
            partition_index=combined_artifact.partition_index,
            partition_summary_path=partition_summary_path,
        )
    except Exception as error:
        if active_partition is not None:
            partition_entries.append(
                _build_completed_partition_summary_entry_from_error(
                    partition_settings=active_partition,
                    partition_run_id=_completed_partition_run_id(run_id, active_partition),
                    error=error,
                )
            )
            setattr(error, "partition_strategy", active_partition.strategy)
            setattr(error, "partition_count", active_partition.partition_count)
            setattr(error, "partition_index", active_partition.partition_index)
        partition_summary_path = _write_completed_partition_summary(
            settings=settings,
            run_id=run_id,
            partition_settings=partition_settings,
            partition_entries=partition_entries,
            combined_artifact=None,
        )
        setattr(error, "completed_partition_summary_path", partition_summary_path)
        raise


def _combine_completed_partition_artifacts(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    partition_settings: PromotionCompletedPartitionSettings,
    partition_artifacts: list[PromotionOperationalCycleExtractionArtifacts],
) -> PromotionOperationalCycleExtractionArtifacts:
    if not partition_artifacts:
        raise ValueError("At least one completed partition artifact is required before combining.")
    rollup_registry_path = settings.artifacts.partition_rollup_registry_path(run_id)
    validate_partition_completion_for_rollup(
        run_id=run_id,
        partition_strategy=partition_settings.strategy,
        expected_partition_count=partition_settings.partition_count,
        partition_artifacts=partition_artifacts,
        registry_output_path=rollup_registry_path,
    )
    first_frame = pd.read_parquet(partition_artifacts[0].base_path)
    expected_columns = [str(column_name) for column_name in first_frame.columns]
    normalized_frames: list[pd.DataFrame] = []
    child_manifest_paths: list[str] = []
    for artifact in partition_artifacts:
        frame = pd.read_parquet(artifact.base_path)
        if set(frame.columns) != set(expected_columns):
            raise ValueError(
                "Completed partition extraction produced a schema mismatch. All partitions must preserve the same output columns before combination."
            )
        normalized_frames.append(frame.reindex(columns=expected_columns))
        child_manifest_paths.append(artifact.manifest_path)
    combined_frame = pd.concat(normalized_frames, ignore_index=True)
    combined_extracted_at_utc = datetime.now(tz=UTC).isoformat()
    combined_manifest = PromotionExtractionManifest(
        run_id=run_id,
        selection_mode="completed",
        query_version=str(partition_artifacts[0].manifest.get("query_version", "promotion_base_v4")),
        as_of_date=settings.as_of_date.isoformat(),
        extracted_at_utc=combined_extracted_at_utc,
        row_count=int(len(combined_frame.index)),
        column_count=int(len(combined_frame.columns)),
        duplicate_promotion_row_keys=int(
            combined_frame["promotion_row_key"].duplicated().sum()
            if "promotion_row_key" in combined_frame.columns
            else 0
        ),
        advice_source_table=str(
            partition_artifacts[0].manifest.get("advice_source_table", settings.sql.promotion_advice_table)
        ),
        realised_sales_source_table=str(
            partition_artifacts[0].manifest.get(
                "realised_sales_source_table",
                settings.sql.pwlogd_table,
            )
        ),
        columns=tuple(str(column_name) for column_name in combined_frame.columns),
        extraction_mode="live_sql",
        fetch_mode="artifact_concat",
        chunk_mode=str(partition_artifacts[0].manifest.get("chunk_mode", "chunked_fetch")),
        chunk_count=sum(int(artifact.chunk_count or 0) for artifact in partition_artifacts),
        completed_chunk_count=sum(
            int(artifact.completed_chunk_count or 0) for artifact in partition_artifacts
        ),
        cumulative_rows_written=sum(
            int(artifact.cumulative_rows_written or 0) for artifact in partition_artifacts
        ),
        batch_count=sum(int(artifact.batch_count or 0) for artifact in partition_artifacts),
        finalized_batch_count=sum(
            int(artifact.finalized_batch_count or 0) for artifact in partition_artifacts
        ),
        resumed_batch_count=sum(
            int(artifact.resumed_batch_count or 0) for artifact in partition_artifacts
        ),
        rebuilt_batch_count=sum(
            int(artifact.rebuilt_batch_count or 0) for artifact in partition_artifacts
        ),
        total_landed_rows=int(len(combined_frame.index)),
        completion_state="finalized",
        partition_completion_state="finalized",
        resume_state="combined_child_partitions",
        skipped_due_to_existing_completion=False,
        promotion_row_key_checksum_sha256=_compute_promotion_row_key_checksum(combined_frame),
        candidate_promotion_row_count=sum(
            int(artifact.candidate_promotion_row_count or 0) for artifact in partition_artifacts
        ),
        partition_strategy=partition_settings.strategy,
        partition_count=partition_settings.partition_count,
        child_partition_manifest_paths=tuple(child_manifest_paths),
    )
    persisted = PromotionExtractionWriter().write(
        base_frame=combined_frame,
        manifest=combined_manifest,
        artifact_paths=settings.artifacts,
    )
    return PromotionOperationalCycleExtractionArtifacts(
        selection_mode="completed",
        frame=combined_frame,
        base_path=str(persisted.base_path),
        manifest_path=str(persisted.manifest_path),
        rendered_sql_path=None,
        rendered_sql_parameters_path=None,
        telemetry_json_path=None,
        telemetry_csv_path=None,
        diagnostics_summary_json_path=None,
        diagnostics_summary_txt_path=None,
        candidate_promotion_row_count=combined_manifest.candidate_promotion_row_count,
        manifest=combined_manifest.to_dict(),
        extraction_mode="live_sql",
        partition_strategy=partition_settings.strategy,
        partition_count=partition_settings.partition_count,
        fetch_mode="artifact_concat",
        chunk_mode=combined_manifest.chunk_mode,
        chunk_count=combined_manifest.chunk_count,
        completed_chunk_count=combined_manifest.completed_chunk_count,
        cumulative_rows_written=combined_manifest.cumulative_rows_written,
        batch_count=combined_manifest.batch_count,
        finalized_batch_count=combined_manifest.finalized_batch_count,
        resumed_batch_count=combined_manifest.resumed_batch_count,
        rebuilt_batch_count=combined_manifest.rebuilt_batch_count,
        total_landed_rows=combined_manifest.total_landed_rows,
        completion_state=combined_manifest.completion_state,
        partition_completion_state=combined_manifest.partition_completion_state,
        resume_state=combined_manifest.resume_state,
    )


def _build_completed_partition_summary_entry_from_artifact(
    *,
    partition_settings: PromotionCompletedPartitionSettings,
    partition_run_id: str,
    extraction_artifact: PromotionOperationalCycleExtractionArtifacts,
    preflight_result: PromotionExtractionPreflightResult | None,
) -> dict[str, object]:
    telemetry_payload = _read_optional_json(extraction_artifact.telemetry_json_path)
    preflight_payload = _read_optional_json(extraction_artifact.preflight_summary_json_path)
    return {
        "partition_strategy": partition_settings.strategy,
        "partition_count": partition_settings.partition_count,
        "partition_index": partition_settings.partition_index,
        "partition_label": _completed_partition_label(partition_settings),
        "run_id": partition_run_id,
        "extraction_status": telemetry_payload.get("extraction_status", "succeeded"),
        "preflight_verdict": (
            preflight_result.summary.verdict
            if preflight_result is not None
            else extraction_artifact.preflight_verdict or preflight_payload.get("verdict")
        ),
        "preflight_reason": (
            preflight_result.summary.reason
            if preflight_result is not None
            else extraction_artifact.preflight_reason or preflight_payload.get("reason")
        ),
        "recommended_partition_strategy": (
            preflight_result.summary.recommended_partition_strategy
            if preflight_result is not None
            else extraction_artifact.recommended_partition_strategy
            or preflight_payload.get("recommended_partition_strategy")
        ),
        "recommended_partition_count": (
            preflight_result.summary.recommended_partition_count
            if preflight_result is not None
            else extraction_artifact.recommended_partition_count
            or _coerce_optional_int(preflight_payload.get("recommended_partition_count"))
        ),
        "estimated_cost_score": (
            preflight_result.summary.estimated_cost_score
            if preflight_result is not None
            else extraction_artifact.estimated_cost_score
            or _coerce_optional_float(preflight_payload.get("estimated_cost_score"))
        ),
        "estimated_extract_query_seconds": (
            preflight_result.summary.estimated_extract_query_seconds
            if preflight_result is not None
            else extraction_artifact.estimated_extract_query_seconds
            or _coerce_optional_float(preflight_payload.get("estimated_extract_query_seconds"))
        ),
        "cost_model_version": (
            preflight_result.summary.cost_model_version
            if preflight_result is not None
            else extraction_artifact.cost_model_version or preflight_payload.get("cost_model_version")
        ),
        "candidate_promotion_row_count": extraction_artifact.candidate_promotion_row_count,
        "candidate_store_sku_count": (
            preflight_result.summary.candidate_store_sku_count
            if preflight_result is not None
            else _coerce_optional_int(preflight_payload.get("candidate_store_sku_count"))
        ),
        "candidate_window_count": (
            preflight_result.summary.candidate_window_count
            if preflight_result is not None
            else _coerce_optional_int(preflight_payload.get("candidate_window_count"))
        ),
        "candidate_window_span_days_total": (
            preflight_result.summary.candidate_window_span_days_total
            if preflight_result is not None
            else _coerce_optional_int(preflight_payload.get("candidate_window_span_days_total"))
        ),
        "candidate_window_span_days_max": (
            preflight_result.summary.candidate_window_span_days_max
            if preflight_result is not None
            else _coerce_optional_int(preflight_payload.get("candidate_window_span_days_max"))
        ),
        "final_extracted_row_count": int(extraction_artifact.manifest.get("row_count", 0) or 0),
        "phase_elapsed_seconds": telemetry_payload.get("phase_elapsed_seconds"),
        "total_elapsed_seconds": telemetry_payload.get("total_elapsed_seconds"),
        "preflight_summary_json_path": (
            preflight_result.artifacts.summary_json_path if preflight_result is not None else None
        ),
        "preflight_summary_csv_path": (
            preflight_result.artifacts.summary_csv_path if preflight_result is not None else None
        ),
        "rendered_preflight_sql_path": (
            preflight_result.artifacts.rendered_sql_path if preflight_result is not None else None
        ),
        "rendered_preflight_sql_parameters_path": (
            preflight_result.artifacts.rendered_sql_parameters_path
            if preflight_result is not None
            else None
        ),
        "completed_preflight_cost_diagnostic_path": (
            extraction_artifact.completed_preflight_cost_diagnostic_path
        ),
        "proof_fallback_used": extraction_artifact.completed_proof_fallback_used,
        "proof_fallback_mode": extraction_artifact.completed_proof_fallback_mode,
        "proof_fallback_reason": extraction_artifact.completed_proof_fallback_reason,
        "base_path": extraction_artifact.base_path,
        "manifest_path": extraction_artifact.manifest_path,
        "rendered_sql_path": extraction_artifact.rendered_sql_path,
        "rendered_sql_parameters_path": extraction_artifact.rendered_sql_parameters_path,
        "telemetry_json_path": extraction_artifact.telemetry_json_path,
        "telemetry_csv_path": extraction_artifact.telemetry_csv_path,
        "sql_diagnostics_summary_json_path": extraction_artifact.diagnostics_summary_json_path,
        "sql_diagnostics_summary_txt_path": extraction_artifact.diagnostics_summary_txt_path,
        "fetch_mode": extraction_artifact.fetch_mode,
        "chunk_mode": extraction_artifact.chunk_mode,
        "chunk_count": extraction_artifact.chunk_count,
        "completed_chunk_count": extraction_artifact.completed_chunk_count,
        "cumulative_rows_written": extraction_artifact.cumulative_rows_written,
        "batch_count": extraction_artifact.batch_count,
        "finalized_batch_count": extraction_artifact.finalized_batch_count,
        "resumed_batch_count": extraction_artifact.resumed_batch_count,
        "rebuilt_batch_count": extraction_artifact.rebuilt_batch_count,
        "total_landed_rows": extraction_artifact.total_landed_rows,
        "completion_state": extraction_artifact.completion_state,
        "partition_completion_state": extraction_artifact.partition_completion_state,
        "resume_state": extraction_artifact.resume_state,
        "skipped_due_to_existing_completion": extraction_artifact.skipped_due_to_existing_completion,
        "partition_progress_path": extraction_artifact.partition_progress_path,
        "partition_completion_marker_path": extraction_artifact.partition_completion_marker_path,
        "failure_exception_type": telemetry_payload.get("failure_exception_type"),
        "failure_message": telemetry_payload.get("failure_message"),
    }


def _build_completed_partition_summary_entry_from_error(
    *,
    partition_settings: PromotionCompletedPartitionSettings,
    partition_run_id: str,
    error: BaseException,
) -> dict[str, object]:
    telemetry_json_path = getattr(error, "extraction_telemetry_json_path", None)
    telemetry_payload = _read_optional_json(telemetry_json_path)
    return {
        "partition_strategy": partition_settings.strategy,
        "partition_count": partition_settings.partition_count,
        "partition_index": partition_settings.partition_index,
        "partition_label": _completed_partition_label(partition_settings),
        "run_id": partition_run_id,
        "extraction_status": telemetry_payload.get("extraction_status", "failed"),
        "preflight_verdict": getattr(error, "preflight_verdict", None),
        "preflight_reason": getattr(error, "preflight_reason", None),
        "recommended_partition_strategy": getattr(error, "recommended_partition_strategy", None),
        "recommended_partition_count": getattr(error, "recommended_partition_count", None),
        "estimated_cost_score": getattr(error, "estimated_cost_score", None),
        "estimated_extract_query_seconds": getattr(error, "estimated_extract_query_seconds", None),
        "cost_model_version": getattr(error, "cost_model_version", None),
        "candidate_promotion_row_count": telemetry_payload.get("candidate_promotion_row_count"),
        "candidate_store_sku_count": getattr(error, "candidate_store_sku_count", None),
        "candidate_window_count": getattr(error, "candidate_window_count", None),
        "candidate_window_span_days_total": getattr(error, "candidate_window_span_days_total", None),
        "candidate_window_span_days_max": getattr(error, "candidate_window_span_days_max", None),
        "final_extracted_row_count": telemetry_payload.get("row_count"),
        "phase_elapsed_seconds": telemetry_payload.get("phase_elapsed_seconds"),
        "total_elapsed_seconds": telemetry_payload.get("total_elapsed_seconds"),
        "preflight_summary_json_path": getattr(error, "preflight_summary_json_path", None),
        "preflight_summary_csv_path": getattr(error, "preflight_summary_csv_path", None),
        "rendered_preflight_sql_path": getattr(error, "rendered_preflight_sql_path", None),
        "rendered_preflight_sql_parameters_path": getattr(
            error,
            "rendered_preflight_sql_parameters_path",
            None,
        ),
        "completed_preflight_cost_diagnostic_path": getattr(
            error,
            "completed_preflight_cost_diagnostic_path",
            None,
        ),
        "proof_fallback_used": getattr(error, "completed_proof_fallback_used", False),
        "proof_fallback_mode": getattr(error, "completed_proof_fallback_mode", None),
        "proof_fallback_reason": getattr(error, "completed_proof_fallback_reason", None),
        "base_path": getattr(error, "output_parquet_path", None),
        "manifest_path": getattr(error, "output_manifest_path", None),
        "rendered_sql_path": getattr(error, "rendered_sql_path", None),
        "rendered_sql_parameters_path": getattr(error, "rendered_sql_parameters_path", None),
        "telemetry_json_path": telemetry_json_path,
        "telemetry_csv_path": getattr(error, "extraction_telemetry_csv_path", None),
        "sql_diagnostics_summary_json_path": getattr(error, "sql_diagnostics_summary_json_path", None),
        "sql_diagnostics_summary_txt_path": getattr(error, "sql_diagnostics_summary_txt_path", None),
        "fetch_mode": telemetry_payload.get("fetch_mode", "full_fetch"),
        "chunk_mode": telemetry_payload.get("chunk_mode", "full_fetch"),
        "chunk_count": telemetry_payload.get("chunk_count", 0),
        "completed_chunk_count": telemetry_payload.get("completed_chunk_count", 0),
        "cumulative_rows_written": telemetry_payload.get("cumulative_rows_written", 0),
        "batch_count": telemetry_payload.get("batch_count", 0),
        "finalized_batch_count": telemetry_payload.get("finalized_batch_count", 0),
        "resumed_batch_count": telemetry_payload.get("resumed_batch_count", 0),
        "rebuilt_batch_count": telemetry_payload.get("rebuilt_batch_count", 0),
        "total_landed_rows": telemetry_payload.get("total_landed_rows", 0),
        "completion_state": telemetry_payload.get("completion_state"),
        "partition_completion_state": telemetry_payload.get("partition_completion_state"),
        "resume_state": telemetry_payload.get("resume_state"),
        "skipped_due_to_existing_completion": telemetry_payload.get(
            "skipped_due_to_existing_completion",
            False,
        ),
        "partition_progress_path": telemetry_payload.get("output_partition_progress_path"),
        "partition_completion_marker_path": telemetry_payload.get(
            "output_partition_completion_path"
        ),
        "failure_exception_type": telemetry_payload.get("failure_exception_type", type(error).__name__),
        "failure_message": telemetry_payload.get("failure_message", str(error)),
    }


def _write_completed_partition_summary(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    partition_settings: PromotionCompletedPartitionSettings,
    partition_entries: list[dict[str, object]],
    combined_artifact: PromotionOperationalCycleExtractionArtifacts | None,
) -> str:
    summary_path = settings.artifacts.completed_partition_summary_path(run_id)
    partitions_succeeded = sum(
        1 for entry in partition_entries if entry.get("extraction_status") == "succeeded"
    )
    partitions_skipped_due_to_existing_completion = sum(
        1
        for entry in partition_entries
        if bool(entry.get("skipped_due_to_existing_completion", False))
    )
    partitions_resumed_from_incomplete = sum(
        1 for entry in partition_entries if entry.get("resume_state") == "resume_incomplete_partition"
    )
    payload = {
        "run_id": run_id,
        "selection_mode": "completed",
        "partition_strategy": partition_settings.strategy,
        "partition_count": partition_settings.partition_count,
        "partitions_succeeded": partitions_succeeded,
        "partitions_failed": len(partition_entries) - partitions_succeeded,
        "partitions_skipped_due_to_existing_completion": (
            partitions_skipped_due_to_existing_completion
        ),
        "partitions_resumed_from_incomplete": partitions_resumed_from_incomplete,
        "total_candidate_promotion_row_count": sum(
            int(entry.get("candidate_promotion_row_count") or 0) for entry in partition_entries
        ),
        "total_extracted_row_count": (
            int(combined_artifact.manifest.get("row_count", 0) or 0)
            if combined_artifact is not None
            else sum(int(entry.get("final_extracted_row_count") or 0) for entry in partition_entries)
        ),
        "total_chunk_count": sum(int(entry.get("chunk_count") or 0) for entry in partition_entries),
        "total_completed_chunk_count": sum(
            int(entry.get("completed_chunk_count") or 0) for entry in partition_entries
        ),
        "total_batch_count": sum(int(entry.get("batch_count") or 0) for entry in partition_entries),
        "total_finalized_batch_count": sum(
            int(entry.get("finalized_batch_count") or 0) for entry in partition_entries
        ),
        "total_resumed_batch_count": sum(
            int(entry.get("resumed_batch_count") or 0) for entry in partition_entries
        ),
        "total_rebuilt_batch_count": sum(
            int(entry.get("rebuilt_batch_count") or 0) for entry in partition_entries
        ),
        "total_landed_rows": (
            int(combined_artifact.total_landed_rows or 0)
            if combined_artifact is not None
            else sum(int(entry.get("total_landed_rows") or 0) for entry in partition_entries)
        ),
        "combined_fetch_mode": combined_artifact.fetch_mode if combined_artifact is not None else None,
        "combined_chunk_mode": combined_artifact.chunk_mode if combined_artifact is not None else None,
        "combined_completion_state": (
            combined_artifact.completion_state if combined_artifact is not None else None
        ),
        "combined_base_path": combined_artifact.base_path if combined_artifact is not None else None,
        "combined_manifest_path": combined_artifact.manifest_path if combined_artifact is not None else None,
        "partitions": partition_entries,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(summary_path)


def _read_optional_json(path: str | None) -> dict[str, object]:
    if path is None:
        return {}
    candidate = Path(path)
    if not candidate.exists():
        return {}
    return json.loads(candidate.read_text(encoding="utf-8"))


def _completed_partition_run_id(
    run_id: str,
    partition_settings: PromotionCompletedPartitionSettings,
) -> str:
    width = len(str(partition_settings.partition_count))
    partition_index = partition_settings.partition_index or 1
    return (
        f"{run_id}-completed-{partition_settings.strategy}-partition-"
        f"{partition_index:0{width}d}-of-{partition_settings.partition_count:0{width}d}"
    )


def _completed_partition_label(partition_settings: PromotionCompletedPartitionSettings) -> str:
    return f"partition {partition_settings.partition_index}/{partition_settings.partition_count}"


def _validate_artifact_roots(artifact_paths: PromotionArtifactPaths) -> tuple[Path, ...]:
    validate_governed_nas_root(artifact_paths.root)
    roots = tuple(artifact_paths.governed_directory_map().values())
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
    return roots


def _stage_subtask_message(selection_mode: str, execution_mode: str) -> str:
    if execution_mode == "live_sql":
        return f"preparing SQL extraction for {selection_mode} promotions"
    if execution_mode == "smoke_patched_extraction":
        return f"loading patched extraction rows for {selection_mode} promotions"
    return f"materializing synthetic smoke rows for {selection_mode} promotions"


def _resolve_failed_extraction_telemetry(
    *,
    error: BaseException,
    extraction_result,
    settings: PromotionPipelineSettings,
    run_id: str,
    selection_mode: str,
) -> PromotionExtractionTelemetry | None:
    telemetry = getattr(error, "promotion_extraction_telemetry", None)
    if telemetry is None and extraction_result is not None:
        telemetry = extraction_result.telemetry
    if not isinstance(telemetry, PromotionExtractionTelemetry):
        return None
    telemetry.output_parquet_path = str(settings.artifacts.extracted_base_path(run_id))
    telemetry.output_manifest_path = str(settings.artifacts.extracted_manifest_path(run_id))
    if _should_use_chunked_completed_extraction(settings=settings, selection_mode=selection_mode):
        telemetry.output_partition_progress_path = str(
            settings.artifacts.extraction_partition_progress_path(run_id)
        )
        telemetry.output_partition_completion_path = str(
            settings.artifacts.extraction_partition_completion_path(run_id)
        )
    if telemetry.dataframe_write_started_at_utc is not None and telemetry.dataframe_write_completed_at_utc is None:
        telemetry.current_sql_subphase = "writing extracted parquet and manifest"
    telemetry.mark_failure(error, stage=telemetry.current_sql_subphase)
    telemetry.selection_mode = selection_mode
    return telemetry


def _attach_extraction_failure_context(
    error: BaseException,
    observability_artifacts,
    telemetry: PromotionExtractionTelemetry,
) -> None:
    setattr(error, "selection_mode", telemetry.selection_mode)
    setattr(error, "as_of_date", telemetry.as_of_date)
    setattr(error, "current_sql_subphase", telemetry.current_sql_subphase)
    setattr(error, "connect_timeout_seconds", telemetry.connect_timeout_seconds)
    setattr(error, "connect_retry_attempts", telemetry.connect_retry_attempts)
    setattr(error, "connect_retry_backoff_seconds", telemetry.connect_retry_backoff_seconds)
    setattr(error, "connect_attempt_count", telemetry.connect_attempt_count)
    setattr(error, "query_timeout_seconds", telemetry.query_timeout_seconds)
    setattr(error, "rendered_sql_path", telemetry.rendered_sql_path)
    setattr(error, "rendered_sql_parameters_path", telemetry.rendered_sql_parameters_path)
    setattr(error, "output_parquet_path", telemetry.output_parquet_path)
    setattr(error, "output_manifest_path", telemetry.output_manifest_path)
    setattr(error, "output_partition_progress_path", telemetry.output_partition_progress_path)
    setattr(error, "output_partition_completion_path", telemetry.output_partition_completion_path)
    setattr(error, "partition_strategy", telemetry.partition_strategy)
    setattr(error, "partition_count", telemetry.partition_count)
    setattr(error, "partition_index", telemetry.partition_index)
    setattr(error, "fetch_mode", telemetry.fetch_mode)
    setattr(error, "chunk_count", telemetry.chunk_count)
    setattr(error, "completed_chunk_count", telemetry.completed_chunk_count)
    setattr(error, "cumulative_rows_written", telemetry.cumulative_rows_written)
    setattr(error, "partition_completion_state", telemetry.partition_completion_state)
    setattr(error, "resume_state", telemetry.resume_state)
    setattr(
        error,
        "skipped_due_to_existing_completion",
        telemetry.skipped_due_to_existing_completion,
    )
    setattr(error, "extraction_telemetry_json_path", observability_artifacts.telemetry_json_path)
    setattr(error, "extraction_telemetry_csv_path", observability_artifacts.telemetry_csv_path)
    setattr(error, "sql_diagnostics_summary_json_path", observability_artifacts.diagnostics_summary_json_path)
    setattr(error, "sql_diagnostics_summary_txt_path", observability_artifacts.diagnostics_summary_txt_path)


def _run_completed_preflight_probe(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    query_options: PromotionBaseQueryOptions | None,
) -> PromotionExtractionPreflightResult:
    executor = SqlAlchemyMssqlQueryExecutor.from_settings(settings.sql)
    return PromotionBaseExtractor(executor=executor).run_preflight(
        run_id=run_id,
        settings=settings,
        selection_mode="completed",
        query_options=query_options,
    )


def _resolve_completed_preflight_proof_fallback(
    *,
    proof_mode: bool,
    planner_settings: PromotionCompletedPreflightPlannerSettings,
    preflight_result: PromotionExtractionPreflightResult,
) -> tuple[PromotionBaseQueryOptions | None, str | None, str | None]:
    if not proof_mode:
        return None, None, None
    mode = planner_settings.proof_completed_fallback_mode
    rejection_reason = preflight_result.summary.reason
    if mode == "diagnostic_topn":
        limit = planner_settings.proof_completed_fallback_topn_limit
        return (
            PromotionBaseQueryOptions(
                extraction_mode="diagnostic_topn",
                limit_promotions=limit,
            ),
            "diagnostic_topn",
            (
                "Completed preflight rejected full scope in proof mode; "
                f"falling back to diagnostic_topn with limit_promotions={limit}. "
                f"Original rejection: {rejection_reason}"
            ),
        )
    limit = planner_settings.proof_completed_fallback_slice_promotion_count
    return (
        PromotionBaseQueryOptions(
            extraction_mode="diagnostic_topn",
            limit_promotions=limit,
            completed_proof_slice_date_count=COMPLETED_PROOF_SLICE_DATE_COUNT,
        ),
        "proof_slice",
        (
            "Completed preflight rejected full scope in proof mode; "
            f"falling back to proof_slice using bounded promotion count={limit} "
            f"across {COMPLETED_PROOF_SLICE_DATE_COUNT} promotion start dates. "
            f"Original rejection: {rejection_reason}"
        ),
    )


def _write_completed_preflight_cost_diagnostic(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    preflight_result: PromotionExtractionPreflightResult,
    rejection_reason: str | None,
    proof_fallback_used: bool,
    proof_fallback_mode: str | None,
) -> str:
    summary = preflight_result.summary
    phase_elapsed = summary.phase_elapsed_seconds or {}
    preflight_query_execution_seconds = _coerce_optional_float(
        phase_elapsed.get("query_execution")
    )
    multiplier = _coerce_optional_float(
        summary.planner_thresholds.get("preflight_query_execution_seconds_multiplier")
    )
    old_heuristic_estimate = (
        round(preflight_query_execution_seconds * multiplier, 3)
        if preflight_query_execution_seconds is not None and multiplier is not None
        else None
    )
    decomposition = {
        "fixed_overhead_seconds": summary.fixed_overhead_seconds,
        "variable_cost_signal": summary.variable_cost_signal,
    }
    payload = {
        "run_id": run_id,
        "selection_mode": "completed",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "model_version": summary.cost_model_version,
        "candidate_counts": {
            "candidate_promotion_row_count": summary.candidate_promotion_row_count,
            "candidate_store_sku_count": summary.candidate_store_sku_count,
            "candidate_window_count": summary.candidate_window_count,
        },
        "window_span_days": {
            "candidate_window_span_days_total": summary.candidate_window_span_days_total,
            "candidate_window_span_days_max": summary.candidate_window_span_days_max,
        },
        "fixed_vs_variable_cost_decomposition": decomposition,
        "old_heuristic_estimate_extract_query_seconds": old_heuristic_estimate,
        "new_model_estimate_extract_query_seconds": summary.estimated_extract_query_seconds,
        "estimated_cost_score": summary.estimated_cost_score,
        "recommended_partition_count": summary.recommended_partition_count,
        "recommended_partition_strategy": summary.recommended_partition_strategy,
        "rejection_reason": rejection_reason,
        "preflight_verdict": summary.verdict,
        "proof_fallback_used": proof_fallback_used,
        "proof_fallback_mode": proof_fallback_mode,
        "proof_fallback_masquerades_as_full_extraction": False,
    }
    diagnostic_path = settings.artifacts.completed_preflight_cost_diagnostic_path(run_id)
    diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(diagnostic_path)


def _write_completed_preflight_model_learning_diagnostic(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    completed_extraction: PromotionOperationalCycleExtractionArtifacts,
) -> str:
    preflight_payload = _read_optional_json(completed_extraction.preflight_summary_json_path)
    telemetry_payload = _read_optional_json(completed_extraction.telemetry_json_path)
    preflight_phase_elapsed = preflight_payload.get("phase_elapsed_seconds", {})
    extraction_phase_elapsed = telemetry_payload.get("phase_elapsed_seconds", {})
    estimated_extract_query_seconds = _coerce_optional_float(
        preflight_payload.get("estimated_extract_query_seconds")
    )
    actual_extract_query_seconds = _coerce_optional_float(
        extraction_phase_elapsed.get("query_execution")
    )
    estimation_error_seconds = (
        round(actual_extract_query_seconds - estimated_extract_query_seconds, 3)
        if estimated_extract_query_seconds is not None and actual_extract_query_seconds is not None
        else None
    )
    estimation_error_ratio = (
        round(actual_extract_query_seconds / estimated_extract_query_seconds, 3)
        if estimated_extract_query_seconds not in (None, 0.0)
        and actual_extract_query_seconds is not None
        else None
    )
    payload = {
        "run_id": run_id,
        "selection_mode": "completed",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "model_version": preflight_payload.get("cost_model_version"),
        "estimated_extract_query_seconds": estimated_extract_query_seconds,
        "actual_extract_query_seconds": actual_extract_query_seconds,
        "estimation_error_seconds": estimation_error_seconds,
        "estimation_error_ratio": estimation_error_ratio,
        "preflight_query_execution_seconds": _coerce_optional_float(
            preflight_phase_elapsed.get("query_execution")
        ),
        "actual_phase_elapsed_seconds": extraction_phase_elapsed,
        "preflight_summary_json_path": completed_extraction.preflight_summary_json_path,
        "extraction_telemetry_json_path": completed_extraction.telemetry_json_path,
    }
    learning_path = settings.artifacts.completed_preflight_model_learning_diagnostic_path(run_id)
    learning_path.parent.mkdir(parents=True, exist_ok=True)
    learning_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(learning_path)


def _emit_completed_preflight_summary(
    *,
    progress: PromotionOperatorProgress,
    preflight_result: PromotionExtractionPreflightResult,
    partition_label: str | None = None,
) -> None:
    label = (
        f"Preflight completed {partition_label}"
        if partition_label is not None
        else "Preflight completed full completed scope"
    )
    progress.detail(label)
    progress.detail(
        "candidate_promotion_row_count: "
        f"{preflight_result.summary.candidate_promotion_row_count if preflight_result.summary.candidate_promotion_row_count is not None else 'n/a'}"
    )
    progress.detail(
        "candidate_store_sku_count: "
        f"{preflight_result.summary.candidate_store_sku_count if preflight_result.summary.candidate_store_sku_count is not None else 'n/a'}"
    )
    progress.detail(
        "candidate_window_count: "
        f"{preflight_result.summary.candidate_window_count if preflight_result.summary.candidate_window_count is not None else 'n/a'}"
    )
    progress.detail(
        "candidate_window_span_days_total: "
        f"{preflight_result.summary.candidate_window_span_days_total if preflight_result.summary.candidate_window_span_days_total is not None else 'n/a'}"
    )
    progress.detail(
        "candidate_window_span_days_max: "
        f"{preflight_result.summary.candidate_window_span_days_max if preflight_result.summary.candidate_window_span_days_max is not None else 'n/a'}"
    )
    progress.detail(
        "estimated_cost_score: "
        f"{preflight_result.summary.estimated_cost_score if preflight_result.summary.estimated_cost_score is not None else 'n/a'}"
    )
    progress.detail(
        "cost_guardrail_verdict: "
        f"{preflight_result.summary.cost_guardrail_verdict or 'n/a'}"
    )
    progress.detail(
        "cost_guardrail_reason: "
        f"{preflight_result.summary.cost_guardrail_reason or 'n/a'}"
    )
    progress.detail(f"verdict: {preflight_result.summary.verdict}")
    progress.detail(
        "recommended_partition_strategy: "
        f"{preflight_result.summary.recommended_partition_strategy or 'n/a'}"
    )
    progress.detail(
        "recommended_partition_count: "
        f"{preflight_result.summary.recommended_partition_count if preflight_result.summary.recommended_partition_count is not None else 'n/a'}"
    )


def _raise_for_completed_preflight_verdict(
    *,
    preflight_result: PromotionExtractionPreflightResult,
    selection_mode: str,
    as_of_date: str,
) -> None:
    error = PromotionCompletedPreflightRejectedError(preflight_result.summary.reason)
    setattr(error, "selection_mode", selection_mode)
    setattr(error, "as_of_date", as_of_date)
    setattr(error, "current_sql_subphase", "preflight planning")
    setattr(error, "preflight_verdict", preflight_result.summary.verdict)
    setattr(error, "preflight_reason", preflight_result.summary.reason)
    setattr(
        error,
        "recommended_partition_strategy",
        preflight_result.summary.recommended_partition_strategy,
    )
    setattr(
        error,
        "recommended_partition_count",
        preflight_result.summary.recommended_partition_count,
    )
    setattr(error, "estimated_cost_score", preflight_result.summary.estimated_cost_score)
    setattr(
        error,
        "estimated_extract_query_seconds",
        preflight_result.summary.estimated_extract_query_seconds,
    )
    setattr(error, "fixed_overhead_seconds", preflight_result.summary.fixed_overhead_seconds)
    setattr(error, "variable_cost_signal", preflight_result.summary.variable_cost_signal)
    setattr(error, "cost_model_version", preflight_result.summary.cost_model_version)
    setattr(error, "cost_guardrail_verdict", preflight_result.summary.cost_guardrail_verdict)
    setattr(error, "cost_guardrail_reason", preflight_result.summary.cost_guardrail_reason)
    setattr(
        error,
        "candidate_promotion_row_count",
        preflight_result.summary.candidate_promotion_row_count,
    )
    setattr(error, "candidate_store_sku_count", preflight_result.summary.candidate_store_sku_count)
    setattr(error, "candidate_window_count", preflight_result.summary.candidate_window_count)
    setattr(
        error,
        "candidate_window_span_days_total",
        preflight_result.summary.candidate_window_span_days_total,
    )
    setattr(
        error,
        "candidate_window_span_days_max",
        preflight_result.summary.candidate_window_span_days_max,
    )
    setattr(error, "partition_strategy", preflight_result.summary.partition_strategy)
    setattr(error, "partition_count", preflight_result.summary.partition_count)
    setattr(error, "partition_index", preflight_result.summary.partition_index)
    setattr(error, "preflight_summary_json_path", preflight_result.artifacts.summary_json_path)
    setattr(error, "preflight_summary_csv_path", preflight_result.artifacts.summary_csv_path)
    setattr(error, "rendered_preflight_sql_path", preflight_result.artifacts.rendered_sql_path)
    setattr(
        error,
        "rendered_preflight_sql_parameters_path",
        preflight_result.artifacts.rendered_sql_parameters_path,
    )
    raise error


def _with_preflight_artifacts(
    *,
    extraction_artifact: PromotionOperationalCycleExtractionArtifacts,
    preflight_result: PromotionExtractionPreflightResult,
) -> PromotionOperationalCycleExtractionArtifacts:
    return replace(
        extraction_artifact,
        preflight_summary_json_path=preflight_result.artifacts.summary_json_path,
        preflight_summary_csv_path=preflight_result.artifacts.summary_csv_path,
        rendered_preflight_sql_path=preflight_result.artifacts.rendered_sql_path,
        rendered_preflight_sql_parameters_path=preflight_result.artifacts.rendered_sql_parameters_path,
        preflight_verdict=preflight_result.summary.verdict,
        preflight_reason=preflight_result.summary.reason,
        estimated_cost_score=preflight_result.summary.estimated_cost_score,
        estimated_extract_query_seconds=preflight_result.summary.estimated_extract_query_seconds,
        fixed_overhead_seconds=preflight_result.summary.fixed_overhead_seconds,
        variable_cost_signal=preflight_result.summary.variable_cost_signal,
        cost_model_version=preflight_result.summary.cost_model_version,
        cost_guardrail_verdict=preflight_result.summary.cost_guardrail_verdict,
        cost_guardrail_reason=preflight_result.summary.cost_guardrail_reason,
        recommended_partition_strategy=preflight_result.summary.recommended_partition_strategy,
        recommended_partition_count=preflight_result.summary.recommended_partition_count,
    )


def _normalize_stage3_completed_extraction_error(
    *,
    error: BaseException,
    settings: PromotionPipelineSettings,
    run_id: str,
    partition_settings: PromotionCompletedPartitionSettings | None,
) -> Exception:
    if isinstance(error, KeyboardInterrupt):
        normalized: Exception = PromotionCompletedExtractionInterruptedError(
            "Stage 3 completed extraction was interrupted by an operator cancellation signal. "
            "No further extraction retries were attempted."
        )
        setattr(normalized, "stage3_interrupted", True)
        setattr(normalized, "stage3_failure_classification", "interrupted")
    elif _is_stage3_pyodbc_exception_set_failure(error):
        normalized = PromotionMssqlQueryError(
            "Promotions MSSQL driver raised an untyped runtime failure during Stage 3 completed extraction. "
            "Inspect Stage 3 failure diagnostics and SQL observability outputs before rerunning. "
            f"Driver detail: {_normalize_stage3_error_message(error)}"
        )
        setattr(normalized, "stage3_failure_classification", "mssql_driver_runtime_failure")
    elif isinstance(error, PromotionMssqlQueryTimeoutError):
        normalized = error
        setattr(normalized, "stage3_failure_classification", "mssql_query_timeout")
    elif isinstance(error, PromotionCompletedPreflightRejectedError):
        normalized = error
        setattr(normalized, "stage3_failure_classification", "preflight_rejected")
    elif isinstance(error, Exception):
        normalized = error
        setattr(normalized, "stage3_failure_classification", "runtime_failure")
    else:
        normalized = RuntimeError(_normalize_stage3_error_message(error))
        setattr(normalized, "stage3_failure_classification", "runtime_failure")

    if getattr(normalized, "selection_mode", None) is None:
        setattr(normalized, "selection_mode", "completed")
    if getattr(normalized, "as_of_date", None) is None:
        setattr(normalized, "as_of_date", settings.as_of_date.isoformat())
    if getattr(normalized, "completed_stage_failure_label", None) is None:
        setattr(normalized, "completed_stage_failure_label", "stage3_completed_extraction")
    if getattr(normalized, "current_sql_subphase", None) is None:
        if getattr(normalized, "stage3_interrupted", False):
            setattr(normalized, "current_sql_subphase", "operator cancellation")
        else:
            setattr(normalized, "current_sql_subphase", "completed extraction execution")
    if getattr(normalized, "partition_strategy", None) is None and partition_settings is not None:
        setattr(normalized, "partition_strategy", partition_settings.strategy)
    if getattr(normalized, "partition_count", None) is None and partition_settings is not None:
        setattr(normalized, "partition_count", partition_settings.partition_count)
    if getattr(normalized, "partition_index", None) is None and partition_settings is not None:
        setattr(normalized, "partition_index", partition_settings.partition_index)

    setattr(normalized, "stage3_normalized_exception_type", type(normalized).__name__)
    setattr(normalized, "stage3_run_id", run_id)
    return normalized


def _is_stage3_pyodbc_exception_set_failure(error: BaseException) -> bool:
    if not isinstance(error, SystemError):
        return False
    message = _normalize_stage3_error_message(error).lower()
    return "pyodbc" in message and "exception set" in message


def _normalize_stage3_error_message(error: BaseException) -> str:
    message = str(error).strip() or error.__class__.__name__
    return " ".join(message.split())


def _write_stage3_completed_extraction_failure_artifacts(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    error: Exception,
) -> None:
    manifests_root = settings.artifacts.manifests_run_root(run_id)
    manifests_root.mkdir(parents=True, exist_ok=True)
    failure_summary_path = manifests_root / "stage3_completed_extraction_failure_summary.json"
    exception_chain_path = manifests_root / "stage3_completed_extraction_exception_chain.json"
    guardrail_path = manifests_root / "stage3_completed_extraction_guardrail.json"

    rerun_command = (
        "python -m runtime.promotions.run_promotions_operator live "
        f"--as-of-date {settings.as_of_date.isoformat()} --run-preflight"
    )
    partition_strategy = getattr(error, "partition_strategy", None)
    partition_count = getattr(error, "partition_count", None)
    if partition_strategy is not None and partition_count is not None:
        rerun_command += (
            f" --partition-strategy {partition_strategy}"
            f" --partition-count {partition_count}"
        )

    summary_payload = {
        "run_id": run_id,
        "stage_number": 3,
        "stage_name": "Extract completed promotions",
        "selection_mode": "completed",
        "failure_recorded_at_utc": datetime.now(tz=UTC).isoformat(),
        "normalized_exception_type": type(error).__name__,
        "normalized_failure_classification": getattr(
            error,
            "stage3_failure_classification",
            "runtime_failure",
        ),
        "interrupted": bool(getattr(error, "stage3_interrupted", False)),
        "current_sql_subphase": getattr(error, "current_sql_subphase", None),
        "reason": _normalize_stage3_error_message(error),
        "partition_strategy": partition_strategy,
        "partition_count": partition_count,
        "partition_index": getattr(error, "partition_index", None),
        "completed_partition_summary_path": getattr(
            error,
            "completed_partition_summary_path",
            None,
        ),
        "completed_partition_retries_json_path": getattr(
            error,
            "completed_partition_retries_json_path",
            None,
        ),
        "completed_partition_retries_csv_path": getattr(
            error,
            "completed_partition_retries_csv_path",
            None,
        ),
        "preflight_summary_json_path": getattr(error, "preflight_summary_json_path", None),
        "preflight_summary_csv_path": getattr(error, "preflight_summary_csv_path", None),
        "rendered_preflight_sql_path": getattr(error, "rendered_preflight_sql_path", None),
        "rendered_preflight_sql_parameters_path": getattr(
            error,
            "rendered_preflight_sql_parameters_path",
            None,
        ),
        "rendered_sql_path": getattr(error, "rendered_sql_path", None),
        "rendered_sql_parameters_path": getattr(error, "rendered_sql_parameters_path", None),
        "extraction_telemetry_json_path": getattr(error, "extraction_telemetry_json_path", None),
        "extraction_telemetry_csv_path": getattr(error, "extraction_telemetry_csv_path", None),
        "sql_diagnostics_summary_json_path": getattr(
            error,
            "sql_diagnostics_summary_json_path",
            None,
        ),
        "sql_diagnostics_summary_txt_path": getattr(error, "sql_diagnostics_summary_txt_path", None),
        "rerun_recommendation": rerun_command,
    }
    failure_summary_path.write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    exception_chain_payload = {
        "run_id": run_id,
        "stage_number": 3,
        "chain": _build_exception_chain_payload(error),
    }
    exception_chain_path.write_text(
        json.dumps(exception_chain_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    guardrail_payload = {
        "run_id": run_id,
        "stage_number": 3,
        "selection_mode": "completed",
        "interrupted": bool(getattr(error, "stage3_interrupted", False)),
        "failure_classification": getattr(
            error,
            "stage3_failure_classification",
            "runtime_failure",
        ),
        "next_action": "Review Stage 3 failure summary and exception chain artifacts before rerunning.",
        "rerun_recommendation": rerun_command,
    }
    guardrail_path.write_text(
        json.dumps(guardrail_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    setattr(error, "stage3_completed_extraction_failure_summary_path", str(failure_summary_path))
    setattr(error, "stage3_completed_extraction_exception_chain_path", str(exception_chain_path))
    setattr(error, "stage3_completed_extraction_guardrail_path", str(guardrail_path))


def _build_exception_chain_payload(error: BaseException) -> list[dict[str, object]]:
    chain: list[dict[str, object]] = []
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and len(chain) < 12:
        object_id = id(current)
        if object_id in visited:
            break
        visited.add(object_id)
        chain.append(
            {
                "exception_type": type(current).__name__,
                "message": _normalize_stage3_error_message(current),
                "current_sql_subphase": getattr(current, "current_sql_subphase", None),
            }
        )
        current = current.__cause__ or current.__context__
    return chain


def _emit_extraction_failure_context(
    *,
    progress: PromotionOperatorProgress,
    error: BaseException,
) -> None:
    completed_stage_failure_label = getattr(error, "completed_stage_failure_label", None)
    completed_batch_run_id = getattr(error, "completed_batch_run_id", None)
    completed_batch_stage_run_id = getattr(error, "completed_batch_stage_run_id", None)
    completed_stage_base_path = getattr(error, "completed_stage_base_path", None)
    completed_stage_manifest_path = getattr(error, "completed_stage_manifest_path", None)
    completed_sales_history_start_date = getattr(
        error,
        "completed_sales_history_start_date",
        None,
    )
    selection_mode = getattr(error, "selection_mode", None)
    connect_timeout_seconds = getattr(error, "connect_timeout_seconds", None)
    connect_retry_attempts = getattr(error, "connect_retry_attempts", None)
    connect_retry_backoff_seconds = getattr(error, "connect_retry_backoff_seconds", None)
    connect_attempt_count = getattr(error, "connect_attempt_count", None)
    query_timeout_seconds = getattr(error, "query_timeout_seconds", None)
    current_sql_subphase = getattr(error, "current_sql_subphase", None)
    rendered_sql_path = getattr(error, "rendered_sql_path", None)
    rendered_sql_parameters_path = getattr(error, "rendered_sql_parameters_path", None)
    extraction_telemetry_json_path = getattr(error, "extraction_telemetry_json_path", None)
    extraction_telemetry_csv_path = getattr(error, "extraction_telemetry_csv_path", None)
    sql_diagnostics_summary_json_path = getattr(error, "sql_diagnostics_summary_json_path", None)
    sql_diagnostics_summary_txt_path = getattr(error, "sql_diagnostics_summary_txt_path", None)
    partition_strategy = getattr(error, "partition_strategy", None)
    partition_count = getattr(error, "partition_count", None)
    partition_index = getattr(error, "partition_index", None)
    completed_partition_summary_path = getattr(error, "completed_partition_summary_path", None)
    as_of_date = getattr(error, "as_of_date", None)
    preflight_verdict = getattr(error, "preflight_verdict", None)
    preflight_reason = getattr(error, "preflight_reason", None)
    preflight_summary_json_path = getattr(error, "preflight_summary_json_path", None)
    preflight_summary_csv_path = getattr(error, "preflight_summary_csv_path", None)
    rendered_preflight_sql_path = getattr(error, "rendered_preflight_sql_path", None)
    rendered_preflight_sql_parameters_path = getattr(
        error,
        "rendered_preflight_sql_parameters_path",
        None,
    )
    estimated_cost_score = getattr(error, "estimated_cost_score", None)
    cost_guardrail_verdict = getattr(error, "cost_guardrail_verdict", None)
    cost_guardrail_reason = getattr(error, "cost_guardrail_reason", None)
    recommended_partition_strategy = getattr(error, "recommended_partition_strategy", None)
    recommended_partition_count = getattr(error, "recommended_partition_count", None)
    candidate_store_sku_count = getattr(error, "candidate_store_sku_count", None)
    candidate_window_span_days_total = getattr(error, "candidate_window_span_days_total", None)
    completed_partition_retries_json_path = getattr(
        error,
        "completed_partition_retries_json_path",
        None,
    )
    completed_partition_retries_csv_path = getattr(
        error,
        "completed_partition_retries_csv_path",
        None,
    )
    completed_repartition_attempts_tried = getattr(
        error,
        "completed_repartition_attempts_tried",
        None,
    )
    max_completed_repartition_attempts = getattr(
        error,
        "max_completed_repartition_attempts",
        None,
    )
    max_completed_partition_count = getattr(error, "max_completed_partition_count", None)
    stage3_failure_summary_path = getattr(
        error,
        "stage3_completed_extraction_failure_summary_path",
        None,
    )
    stage3_exception_chain_path = getattr(
        error,
        "stage3_completed_extraction_exception_chain_path",
        None,
    )
    stage3_guardrail_path = getattr(error, "stage3_completed_extraction_guardrail_path", None)
    stage3_interrupted = getattr(error, "stage3_interrupted", None)
    stage6_execution_scope = getattr(error, "stage6_execution_scope", None)
    stage6_planner_verdict = getattr(error, "stage6_planner_verdict", None)
    stage6_operator_message = getattr(error, "stage6_operator_message", None)
    stage6_future_extraction_mode = getattr(error, "stage6_future_extraction_mode", None)
    stage6_proof_fallback_used = getattr(error, "stage6_proof_fallback_used", None)
    stage6_proof_fallback_mode = getattr(error, "stage6_proof_fallback_mode", None)
    stage6_proof_fallback_reason = getattr(error, "stage6_proof_fallback_reason", None)
    stage6_guardrail_path = getattr(error, "stage6_future_extraction_guardrail_path", None)
    stage6_plan_path = getattr(error, "stage6_future_extraction_plan_path", None)
    stage6_failure_summary_path = getattr(
        error,
        "stage6_future_extraction_failure_summary_path",
        None,
    )

    if selection_mode is not None:
        progress.detail(f"mode: {selection_mode}")
    if completed_stage_failure_label is not None:
        progress.detail(f"failed_completed_stage: {completed_stage_failure_label}")
    if completed_batch_run_id is not None:
        progress.detail(f"failed_completed_batch_run_id: {completed_batch_run_id}")
    if completed_batch_stage_run_id is not None:
        progress.detail(f"failed_completed_stage_run_id: {completed_batch_stage_run_id}")
    if current_sql_subphase is not None:
        progress.detail(f"failed_sql_subphase: {current_sql_subphase}")
    if completed_sales_history_start_date is not None:
        progress.detail(
            "completed_sales_history_start_date_applied: "
            f"{completed_sales_history_start_date}"
        )
    if partition_strategy is not None and partition_count is not None and partition_index is not None:
        progress.detail(
            f"failed_partition: {partition_index}/{partition_count} ({partition_strategy})"
        )
    if preflight_verdict is not None:
        progress.detail(f"preflight_verdict: {preflight_verdict}")
    if preflight_reason is not None:
        progress.detail(f"preflight_reason: {preflight_reason}")
    if candidate_store_sku_count is not None:
        progress.detail(f"candidate_store_sku_count: {candidate_store_sku_count}")
    if candidate_window_span_days_total is not None:
        progress.detail(f"candidate_window_span_days_total: {candidate_window_span_days_total}")
    if recommended_partition_strategy is not None:
        progress.detail(f"recommended_partition_strategy: {recommended_partition_strategy}")
    if recommended_partition_count is not None:
        progress.detail(f"recommended_partition_count: {recommended_partition_count}")
    if completed_repartition_attempts_tried is not None:
        progress.detail(
            f"completed_repartition_attempts_tried: {completed_repartition_attempts_tried}"
        )
    if max_completed_repartition_attempts is not None:
        progress.detail(
            f"max_completed_repartition_attempts: {max_completed_repartition_attempts}"
        )
    if max_completed_partition_count is not None:
        progress.detail(f"max_completed_partition_count: {max_completed_partition_count}")
    if connect_timeout_seconds is not None:
        progress.detail(f"connect_timeout_seconds_applied: {connect_timeout_seconds}")
    if connect_retry_attempts is not None:
        progress.detail(f"connect_retry_attempts: {connect_retry_attempts}")
    if connect_retry_backoff_seconds is not None:
        progress.detail(f"connect_retry_backoff_seconds: {connect_retry_backoff_seconds}")
    if connect_attempt_count is not None:
        progress.detail(f"connect_attempt_count: {connect_attempt_count}")
    if query_timeout_seconds is not None:
        progress.detail(f"query_timeout_seconds_applied: {query_timeout_seconds}")
    if estimated_cost_score is not None:
        progress.detail(f"estimated_cost_score: {estimated_cost_score}")
    if cost_guardrail_verdict is not None:
        progress.detail(f"cost_guardrail_verdict: {cost_guardrail_verdict}")
    if cost_guardrail_reason is not None:
        progress.detail(f"cost_guardrail_reason: {cost_guardrail_reason}")
    if preflight_summary_json_path is not None:
        progress.detail(f"preflight_summary_json_path: {preflight_summary_json_path}")
    if preflight_summary_csv_path is not None:
        progress.detail(f"preflight_summary_csv_path: {preflight_summary_csv_path}")
    if rendered_preflight_sql_path is not None:
        progress.detail(f"rendered_preflight_sql_path: {rendered_preflight_sql_path}")
    if rendered_preflight_sql_parameters_path is not None:
        progress.detail(
            f"rendered_preflight_sql_parameters_path: {rendered_preflight_sql_parameters_path}"
        )
    if rendered_sql_path is not None:
        progress.detail(f"rendered_sql_path: {rendered_sql_path}")
    if rendered_sql_parameters_path is not None:
        progress.detail(f"rendered_sql_parameters_path: {rendered_sql_parameters_path}")
    if completed_stage_base_path is not None:
        progress.detail(f"completed_stage_base_path: {completed_stage_base_path}")
    if completed_stage_manifest_path is not None:
        progress.detail(f"completed_stage_manifest_path: {completed_stage_manifest_path}")
    if extraction_telemetry_json_path is not None:
        progress.detail(f"extraction_telemetry_json_path: {extraction_telemetry_json_path}")
    if extraction_telemetry_csv_path is not None:
        progress.detail(f"extraction_telemetry_csv_path: {extraction_telemetry_csv_path}")
    if sql_diagnostics_summary_json_path is not None:
        progress.detail(f"sql_diagnostics_summary_json_path: {sql_diagnostics_summary_json_path}")
    if sql_diagnostics_summary_txt_path is not None:
        progress.detail(f"sql_diagnostics_summary_txt_path: {sql_diagnostics_summary_txt_path}")
    if completed_partition_summary_path is not None:
        progress.detail(f"completed_partition_summary_path: {completed_partition_summary_path}")
    if stage3_failure_summary_path is not None:
        progress.detail(f"stage3_completed_extraction_failure_summary_path: {stage3_failure_summary_path}")
    if stage3_exception_chain_path is not None:
        progress.detail(f"stage3_completed_extraction_exception_chain_path: {stage3_exception_chain_path}")
    if stage3_guardrail_path is not None:
        progress.detail(f"stage3_completed_extraction_guardrail_path: {stage3_guardrail_path}")
    if stage3_interrupted is not None:
        progress.detail(f"stage3_interrupted: {str(bool(stage3_interrupted)).lower()}")
    if stage6_execution_scope is not None:
        progress.detail(f"stage6_execution_scope: {stage6_execution_scope}")
    if stage6_future_extraction_mode is not None:
        progress.detail(f"stage6_future_extraction_mode: {stage6_future_extraction_mode}")
    if stage6_proof_fallback_used is not None:
        progress.detail(
            f"stage6_proof_fallback_used: {str(bool(stage6_proof_fallback_used)).lower()}"
        )
    if stage6_proof_fallback_mode is not None:
        progress.detail(f"stage6_proof_fallback_mode: {stage6_proof_fallback_mode}")
    if stage6_proof_fallback_reason is not None:
        progress.detail(f"stage6_proof_fallback_reason: {stage6_proof_fallback_reason}")
    if stage6_planner_verdict is not None:
        progress.detail(f"stage6_planner_verdict: {stage6_planner_verdict}")
    if stage6_operator_message is not None:
        progress.detail(f"stage6_operator_message: {stage6_operator_message}")
    if stage6_guardrail_path is not None:
        progress.detail(f"stage6_future_extraction_guardrail_path: {stage6_guardrail_path}")
    if stage6_plan_path is not None:
        progress.detail(f"stage6_future_extraction_plan_path: {stage6_plan_path}")
    if stage6_failure_summary_path is not None:
        progress.detail(
            f"stage6_future_extraction_failure_summary_path: {stage6_failure_summary_path}"
        )
    if completed_partition_retries_json_path is not None:
        progress.detail(
            f"completed_partition_retries_json_path: {completed_partition_retries_json_path}"
        )
    if completed_partition_retries_csv_path is not None:
        progress.detail(
            f"completed_partition_retries_csv_path: {completed_partition_retries_csv_path}"
        )
    if selection_mode is not None and as_of_date is not None:
        suggestion = (
            "suggestion: python -m runtime.promotions.inspect_promotions_sql_extraction "
            f"--selection-mode {selection_mode} --as-of-date {as_of_date} "
        )
        if partition_strategy is not None and partition_count is not None and partition_index is not None:
            suggestion += (
                f"--partition-strategy {partition_strategy} --partition-count {partition_count} "
                f"--partition-index {partition_index} "
            )
        suggestion += "--run-row-count-probe --save-rendered-sql --extraction-mode diagnostic_topn --limit-promotions 25"
        progress.detail(suggestion)


def _build_completed_partitioning_from_args(
    args: argparse.Namespace,
) -> PromotionCompletedPartitionSettings | None:
    if (
        args.partition_strategy is None
        and args.partition_count is None
        and args.partition_index is None
    ):
        return None
    if args.partition_strategy is None or args.partition_count is None:
        raise ValueError(
            "partition_strategy and partition_count must both be provided when enabling completed partitioning."
        )
    return PromotionCompletedPartitionSettings(
        strategy=args.partition_strategy,
        partition_count=args.partition_count,
        partition_index=args.partition_index,
    )


def _build_completed_preflight_planner_from_args(
    args: argparse.Namespace,
) -> PromotionCompletedPreflightPlannerSettings:
    defaults = PromotionCompletedPreflightPlannerSettings()
    
    # Apply proof-mode constraint: cap max_completed_partition_count if proof_max_partitions is set
    max_partition_count = args.max_completed_partition_count
    proof_mode = getattr(args, "proof_mode", False)
    proof_max_partitions = getattr(args, "proof_max_partitions", None)
    if proof_mode and proof_max_partitions is not None:
        max_partition_count = min(max_partition_count, proof_max_partitions)
    
    return PromotionCompletedPreflightPlannerSettings(
        run_preflight=args.run_preflight,
        planner_only=args.planner_only,
        auto_repartition_completed=_parse_bool_arg(args.auto_repartition_completed),
        max_completed_repartition_attempts=args.max_completed_repartition_attempts,
        max_completed_partition_count=max_partition_count,
        max_candidate_promotion_rows=(
            args.max_candidate_promotion_rows
            if args.max_candidate_promotion_rows is not None
            else defaults.max_candidate_promotion_rows
        ),
        max_candidate_store_sku=(
            args.max_candidate_store_sku
            if args.max_candidate_store_sku is not None
            else defaults.max_candidate_store_sku
        ),
        max_window_span_days_total=(
            args.max_window_span_days_total
            if args.max_window_span_days_total is not None
            else defaults.max_window_span_days_total
        ),
        max_window_span_days_max=(
            args.max_window_span_days_max
            if args.max_window_span_days_max is not None
            else defaults.max_window_span_days_max
        ),
        proof_completed_fallback_mode=(
            args.proof_completed_fallback_mode
            if args.proof_completed_fallback_mode is not None
            else defaults.proof_completed_fallback_mode
        ),
        proof_completed_fallback_topn_limit=(
            args.proof_completed_fallback_topn_limit
            if args.proof_completed_fallback_topn_limit is not None
            else defaults.proof_completed_fallback_topn_limit
        ),
        proof_completed_fallback_slice_promotion_count=(
            args.proof_completed_fallback_slice_promotions
            if args.proof_completed_fallback_slice_promotions is not None
            else defaults.proof_completed_fallback_slice_promotion_count
        ),
        default_partition_strategy=defaults.default_partition_strategy,
    )


def _parse_bool_arg(raw_value: str) -> bool:
    return raw_value == "true"


if __name__ == "__main__":
    main()