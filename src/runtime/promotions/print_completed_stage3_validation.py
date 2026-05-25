from __future__ import annotations

"""Print a compact staged Stage-3 validation summary for one completed partition run."""

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, TextIO

from runtime.promotions.config import PromotionArtifactPaths


_BATCH_RUN_ID_PATTERN = re.compile(r"-batch-(\d+)$")
_COMPLETED_SQL_EXTRACTOR_STAGES = frozenset(
    {
        "completed_base",
        "completed_window_aggregates",
        "completed_transaction_aggregates",
    }
)


@dataclass(frozen=True)
class PromotionCompletedStage3ValidationRecord:
    stage_name: str
    partition_index: int | None
    partition_count: int | None
    batch_number: int | None
    row_window_start: int | None
    row_window_end: int | None
    elapsed_seconds: float | None
    rows_written: int | None
    rendered_sql_path: str | None
    telemetry_path: str | None
    diagnostics_path: str | None
    completion_marker_path: str | None
    completed_sales_history_start_date: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionCompletedStage3FollowUpStageSummary:
    stage_name: str
    elapsed_seconds: float | None
    rows_written: int
    rendered_sql_paths: tuple[str, ...]
    telemetry_paths: tuple[str, ...]
    diagnostics_paths: tuple[str, ...]
    completion_marker_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionCompletedStage3FollowUpSummary:
    partition_index: int | None
    partition_count: int | None
    total_candidate_rows: int | None
    total_extracted_rows: int
    landed_batch_count: int
    lower_bound_date_applied: str | None
    partition_completion_marker_path: str
    partition_progress_path: str
    per_stage: tuple[PromotionCompletedStage3FollowUpStageSummary, ...]
    safe_to_resume_reuse: bool
    status: str
    success_summary: str
    warning_summary: str | None
    failure_summary: str | None
    failure_classification: str | None
    planner_verdict: str | None = None
    planner_reason: str | None = None
    recommended_partition_strategy: str | None = None
    recommended_partition_count: int | None = None
    observed_max_grouped_live_window_span_days: int | None = None
    observed_max_live_promo_days: int | None = None
    theoretical_completed_window_span_days_max: int | None = None
    preflight_summary_json_path: str | None = None
    rendered_preflight_sql_path: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "partition_index": self.partition_index,
            "partition_count": self.partition_count,
            "total_candidate_rows": self.total_candidate_rows,
            "total_extracted_rows": self.total_extracted_rows,
            "landed_batch_count": self.landed_batch_count,
            "lower_bound_date_applied": self.lower_bound_date_applied,
            "partition_completion_marker_path": self.partition_completion_marker_path,
            "partition_progress_path": self.partition_progress_path,
            "per_stage": [stage.to_dict() for stage in self.per_stage],
            "safe_to_resume_reuse": self.safe_to_resume_reuse,
            "status": self.status,
            "success_summary": self.success_summary,
            "warning_summary": self.warning_summary,
            "failure_summary": self.failure_summary,
            "failure_classification": self.failure_classification,
            "planner_verdict": self.planner_verdict,
            "planner_reason": self.planner_reason,
            "recommended_partition_strategy": self.recommended_partition_strategy,
            "recommended_partition_count": self.recommended_partition_count,
            "observed_max_grouped_live_window_span_days": self.observed_max_grouped_live_window_span_days,
            "observed_max_live_promo_days": self.observed_max_live_promo_days,
            "theoretical_completed_window_span_days_max": self.theoretical_completed_window_span_days_max,
            "preflight_summary_json_path": self.preflight_summary_json_path,
            "rendered_preflight_sql_path": self.rendered_preflight_sql_path,
            "note": self.note,
        }

@dataclass(frozen=True)
class PromotionCompletedStage3ValidationSummary:
    run_id: str
    partition_index: int | None
    partition_count: int | None
    completed_sales_history_start_date: str | None
    records: tuple[PromotionCompletedStage3ValidationRecord, ...]
    follow_up: PromotionCompletedStage3FollowUpSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "partition_index": self.partition_index,
            "partition_count": self.partition_count,
            "completed_sales_history_start_date": self.completed_sales_history_start_date,
            "records": [record.to_dict() for record in self.records],
            "follow_up": self.follow_up.to_dict(),
        }


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    artifact_paths = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
        enable_local_inspection_copy=False,
        env_file=args.env_file,
    )
    summary = collect_completed_stage3_validation_summary(
        artifact_paths=artifact_paths,
        run_id=args.run_id,
        partition_index=args.partition_index,
        partition_count=args.partition_count,
    )
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        return
    render_completed_stage3_validation_summary(summary, stream=sys.stdout)


def collect_completed_stage3_validation_summary(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    partition_index: int | None = None,
    partition_count: int | None = None,
) -> PromotionCompletedStage3ValidationSummary:
    partition_manifest_path = artifact_paths.extracted_manifest_path(run_id)
    if not partition_manifest_path.exists():
        preflight_fallback = _build_preflight_rejected_summary_if_available(
            artifact_paths=artifact_paths,
            run_id=run_id,
            partition_index=partition_index,
            partition_count=partition_count,
        )
        if preflight_fallback is not None:
            return preflight_fallback
        raise FileNotFoundError(
            "Completed partition manifest not found for run_id="
            f"{run_id}: expected {partition_manifest_path}"
        )
    partition_manifest = _load_json(partition_manifest_path)
    effective_partition_index = partition_index
    effective_partition_count = partition_count
    if effective_partition_index is None:
        effective_partition_index = _as_int(partition_manifest.get("partition_index"))
    if effective_partition_count is None:
        effective_partition_count = _as_int(partition_manifest.get("partition_count"))

    partition_progress = _load_json_if_exists(
        artifact_paths.extraction_partition_progress_path(run_id)
    )
    batch_row_count = _as_int(partition_progress.get("batch_row_count"))

    fallback_history_start_date = _as_str(
        partition_manifest.get("completed_sales_history_start_date")
    )
    partition_progress_path = artifact_paths.extraction_partition_progress_path(run_id)
    partition_completion_marker_path = artifact_paths.extraction_partition_completion_path(run_id)
    partition_diagnostics_path = artifact_paths.sql_diagnostics_summary_json_path(run_id)
    partition_progress = _load_json_if_exists(partition_progress_path)
    partition_completion_marker = _load_json_if_exists(partition_completion_marker_path)
    partition_diagnostics = _load_json_if_exists(partition_diagnostics_path)

    stage_accumulators: dict[str, dict[str, object]] = {}
    warnings: list[str] = []
    failure_signals: list[str] = []

    records: list[PromotionCompletedStage3ValidationRecord] = []
    landed_batch_count = 0
    total_candidate_rows = 0
    candidate_rows_present = False
    total_batch_rows = 0

    for batch_manifest_path in partition_manifest.get("child_batch_manifest_paths", []):
        landed_batch_count += 1
        batch_manifest = _load_json(Path(str(batch_manifest_path)))
        batch_candidate_rows = _as_int(batch_manifest.get("candidate_promotion_row_count"))
        if batch_candidate_rows is not None:
            total_candidate_rows += batch_candidate_rows
            candidate_rows_present = True
        batch_manifest_row_count = _as_int(batch_manifest.get("row_count"))
        if batch_manifest_row_count is not None:
            total_batch_rows += batch_manifest_row_count
        batch_run_id = _as_str(batch_manifest.get("run_id")) or _derive_run_id_from_path(
            Path(str(batch_manifest_path))
        )
        batch_number = _parse_batch_number(batch_run_id)
        row_window_start, row_window_end = _resolve_row_window(
            batch_number=batch_number,
            batch_row_count=batch_row_count,
        )
        batch_history_start_date = _as_str(
            batch_manifest.get("completed_sales_history_start_date")
        ) or fallback_history_start_date

        child_stage_manifest_paths = batch_manifest.get("child_stage_manifest_paths", ())
        for child_stage_manifest_path in child_stage_manifest_paths:
            stage_manifest = _load_json(Path(str(child_stage_manifest_path)))
            stage_run_id = _as_str(stage_manifest.get("run_id")) or _derive_run_id_from_path(
                Path(str(child_stage_manifest_path))
            )
            telemetry_path = artifact_paths.extraction_telemetry_json_path(stage_run_id)
            diagnostics_path = artifact_paths.sql_diagnostics_summary_json_path(stage_run_id)
            completion_marker_path = artifact_paths.extraction_partition_completion_path(stage_run_id)
            rendered_sql_path = artifact_paths.manifests_run_root(stage_run_id) / "rendered_sql.sql"
            telemetry_payload = _load_json_if_exists(telemetry_path)
            diagnostics_payload = _load_json_if_exists(diagnostics_path)
            _collect_failure_signal_from_payload(diagnostics_payload, failure_signals)
            records.append(
                PromotionCompletedStage3ValidationRecord(
                    stage_name=_as_str(stage_manifest.get("extraction_stage"))
                    or _as_str(stage_manifest.get("stage_name"))
                    or "unknown_stage",
                    partition_index=effective_partition_index,
                    partition_count=effective_partition_count,
                    batch_number=batch_number,
                    row_window_start=row_window_start,
                    row_window_end=row_window_end,
                    elapsed_seconds=_as_float(telemetry_payload.get("total_elapsed_seconds")),
                    rows_written=_as_int(stage_manifest.get("row_count")),
                    rendered_sql_path=str(rendered_sql_path),
                    telemetry_path=str(telemetry_path),
                    diagnostics_path=str(diagnostics_path),
                    completion_marker_path=str(completion_marker_path),
                    completed_sales_history_start_date=(
                        _as_str(stage_manifest.get("completed_sales_history_start_date"))
                        or batch_history_start_date
                    ),
                )
            )
            _accumulate_stage_summary(
                stage_accumulators=stage_accumulators,
                stage_name=(
                    _as_str(stage_manifest.get("extraction_stage"))
                    or _as_str(stage_manifest.get("stage_name"))
                    or "unknown_stage"
                ),
                elapsed_seconds=_as_float(telemetry_payload.get("total_elapsed_seconds")),
                rows_written=_as_int(stage_manifest.get("row_count")),
                rendered_sql_path=str(rendered_sql_path),
                telemetry_path=str(telemetry_path),
                diagnostics_path=str(diagnostics_path),
                completion_marker_path=str(completion_marker_path),
            )

        batch_telemetry_path = artifact_paths.extraction_telemetry_json_path(batch_run_id)
        batch_telemetry_payload = _load_json_if_exists(batch_telemetry_path)
        batch_diagnostics_path = artifact_paths.sql_diagnostics_summary_json_path(batch_run_id)
        batch_diagnostics_payload = _load_json_if_exists(batch_diagnostics_path)
        _collect_failure_signal_from_payload(batch_diagnostics_payload, failure_signals)
        records.append(
            PromotionCompletedStage3ValidationRecord(
                stage_name="completed_final_assembler",
                partition_index=effective_partition_index,
                partition_count=effective_partition_count,
                batch_number=batch_number,
                row_window_start=row_window_start,
                row_window_end=row_window_end,
                elapsed_seconds=_as_float(batch_telemetry_payload.get("total_elapsed_seconds")),
                rows_written=_as_int(batch_manifest.get("row_count")),
                rendered_sql_path=None,
                telemetry_path=str(batch_telemetry_path),
                diagnostics_path=str(artifact_paths.sql_diagnostics_summary_json_path(batch_run_id)),
                completion_marker_path=str(
                    artifact_paths.extraction_partition_completion_path(batch_run_id)
                ),
                completed_sales_history_start_date=batch_history_start_date,
            )
        )
        _accumulate_stage_summary(
            stage_accumulators=stage_accumulators,
            stage_name="completed_final_assembler",
            elapsed_seconds=_as_float(batch_telemetry_payload.get("total_elapsed_seconds")),
            rows_written=_as_int(batch_manifest.get("row_count")),
            rendered_sql_path=None,
            telemetry_path=str(batch_telemetry_path),
            diagnostics_path=str(batch_diagnostics_path),
            completion_marker_path=str(artifact_paths.extraction_partition_completion_path(batch_run_id)),
        )

    if not candidate_rows_present:
        manifest_candidate_rows = _as_int(partition_manifest.get("candidate_promotion_row_count"))
        progress_candidate_rows = _as_int(partition_progress.get("candidate_promotion_row_count"))
        if manifest_candidate_rows is not None:
            total_candidate_rows = manifest_candidate_rows
            candidate_rows_present = True
        elif progress_candidate_rows is not None:
            total_candidate_rows = progress_candidate_rows
            candidate_rows_present = True

    _collect_failure_signal_from_payload(partition_diagnostics, failure_signals)
    failure_message = _as_str(partition_progress.get("failure_message"))
    if failure_message:
        failure_signals.append(failure_message)

    lower_bound_values = {
        record.completed_sales_history_start_date
        for record in records
        if record.completed_sales_history_start_date
    }
    lower_bound_date_applied = fallback_history_start_date
    if lower_bound_date_applied is None and lower_bound_values:
        lower_bound_date_applied = sorted(lower_bound_values)[0]
    if len(lower_bound_values) > 1:
        warnings.append(
            "Inconsistent completed_sales_history_start_date values across staged records."
        )

    partition_completion_state = _as_str(
        partition_completion_marker.get("partition_completion_state")
    )
    completion_state = _as_str(partition_completion_marker.get("completion_state"))
    has_partition_completion = partition_completion_marker_path.exists()
    if not has_partition_completion:
        warnings.append("Partition completion marker is missing.")
    all_stage_completion_markers_present = all(
        Path(record.completion_marker_path).exists()
        for record in records
        if record.completion_marker_path is not None
    )
    if not all_stage_completion_markers_present:
        warnings.append("One or more staged completion markers are missing.")

    partition_manifest_rows = _as_int(partition_manifest.get("row_count"))
    progress_total_landed_rows = _as_int(partition_progress.get("total_landed_rows"))
    assembled_partition_parquet_path = artifact_paths.extracted_base_path(run_id)
    has_assembled_partition_parquet = assembled_partition_parquet_path.exists()

    stages_by_name = {record.stage_name: record for record in records}
    required_completed_stages_present = all(
        stage_name in stages_by_name for stage_name in _COMPLETED_SQL_EXTRACTOR_STAGES
    )
    required_completed_stage_markers_present = all(
        (stages_by_name.get(stage_name) is not None)
        and Path(stages_by_name[stage_name].completion_marker_path or "").exists()
        for stage_name in _COMPLETED_SQL_EXTRACTOR_STAGES
    )
    required_completed_stage_rendered_sql_present = all(
        (stages_by_name.get(stage_name) is not None)
        and Path(stages_by_name[stage_name].rendered_sql_path or "").exists()
        for stage_name in _COMPLETED_SQL_EXTRACTOR_STAGES
    )
    final_assembler_record = stages_by_name.get("completed_final_assembler")
    final_assembler_completion_marker_present = (
        final_assembler_record is not None
        and Path(final_assembler_record.completion_marker_path or "").exists()
    )
    final_assembler_ready = (
        final_assembler_completion_marker_present
        or has_assembled_partition_parquet
        or partition_completion_state == "finalized"
    )

    stage_records_valid_for_success = (
        required_completed_stages_present
        and required_completed_stage_markers_present
        and required_completed_stage_rendered_sql_present
        and final_assembler_ready
    )

    if not required_completed_stages_present:
        failure_signals.append("missing required completed child stage manifests")
    if not required_completed_stage_markers_present:
        failure_signals.append("missing required completed child stage completion markers")
    if not required_completed_stage_rendered_sql_present:
        failure_signals.append("missing required completed child stage rendered sql outputs")
    if not final_assembler_ready:
        failure_signals.append("missing final assembler completion evidence")
    if not has_assembled_partition_parquet:
        failure_signals.append("missing assembled partition parquet output")

    if (
        partition_manifest_rows is not None
        and total_batch_rows > 0
        and total_batch_rows != partition_manifest_rows
    ):
        failure_signals.append("row count mismatch between partition manifest and batch manifests")
    if (
        partition_manifest_rows is not None
        and progress_total_landed_rows is not None
        and partition_manifest_rows != progress_total_landed_rows
    ):
        failure_signals.append("row count mismatch between partition manifest and partition progress")

    failure_classification = _classify_failure_signals(
        failure_signals,
        partition_completion_state=partition_completion_state,
        completion_state=completion_state,
        has_partition_completion=has_partition_completion,
    )
    if failure_classification == "resume / completion-marker inconsistency":
        warnings.append("Resume/completion marker consistency check failed.")

    per_stage = tuple(
        PromotionCompletedStage3FollowUpStageSummary(
            stage_name=stage_name,
            elapsed_seconds=_as_float(values.get("elapsed_seconds")),
            rows_written=int(values.get("rows_written", 0) or 0),
            rendered_sql_paths=tuple(sorted(values.get("rendered_sql_paths", set()))),
            telemetry_paths=tuple(sorted(values.get("telemetry_paths", set()))),
            diagnostics_paths=tuple(sorted(values.get("diagnostics_paths", set()))),
            completion_marker_paths=tuple(sorted(values.get("completion_marker_paths", set()))),
        )
        for stage_name, values in sorted(stage_accumulators.items())
    )

    total_extracted_rows = (
        partition_manifest_rows
        or progress_total_landed_rows
        or total_batch_rows
    )
    success_criteria_met = (
        partition_completion_state == "finalized"
        and total_extracted_rows > 0
        and landed_batch_count >= 1
        and stage_records_valid_for_success
    )
    safe_to_resume_reuse = (
        has_partition_completion
        and partition_completion_state == "finalized"
        and (completion_state in (None, "finalized"))
        and has_assembled_partition_parquet
        and stage_records_valid_for_success
        and failure_classification is None
    )
    status = "success"
    if failure_classification is not None:
        status = "failure"
    elif not success_criteria_met:
        status = "warning"
    elif warnings:
        status = "warning"

    success_summary = (
        "Stage 3 completed partition artifacts are consolidated and readable; "
        f"extracted_rows={total_extracted_rows}, landed_batch_count={landed_batch_count}."
    )
    warning_summary = " ".join(warnings) if warnings else None
    failure_summary = None
    if failure_classification is not None:
        failure_summary = (
            f"Stage 3 follow-up detected a failure classified as: {failure_classification}."
        )

    follow_up = PromotionCompletedStage3FollowUpSummary(
        partition_index=effective_partition_index,
        partition_count=effective_partition_count,
        total_candidate_rows=(total_candidate_rows if candidate_rows_present else None),
        total_extracted_rows=total_extracted_rows,
        landed_batch_count=landed_batch_count,
        lower_bound_date_applied=lower_bound_date_applied,
        partition_completion_marker_path=str(partition_completion_marker_path),
        partition_progress_path=str(partition_progress_path),
        per_stage=per_stage,
        safe_to_resume_reuse=safe_to_resume_reuse,
        status=status,
        success_summary=success_summary,
        warning_summary=warning_summary,
        failure_summary=failure_summary,
        failure_classification=failure_classification,
    )

    return PromotionCompletedStage3ValidationSummary(
        run_id=run_id,
        partition_index=effective_partition_index,
        partition_count=effective_partition_count,
        completed_sales_history_start_date=fallback_history_start_date,
        records=tuple(records),
        follow_up=follow_up,
    )


def render_completed_stage3_validation_summary(
    summary: PromotionCompletedStage3ValidationSummary,
    *,
    stream: TextIO,
) -> None:
    print("PROMOTIONS COMPLETED STAGE 3 VALIDATION", file=stream)
    print(f"run_id: {summary.run_id}", file=stream)
    print(
        "partition_index: "
        f"{summary.partition_index if summary.partition_index is not None else 'n/a'}",
        file=stream,
    )
    print(
        "partition_count: "
        f"{summary.partition_count if summary.partition_count is not None else 'n/a'}",
        file=stream,
    )
    print(
        "completed_sales_history_start_date: "
        f"{summary.completed_sales_history_start_date or 'n/a'}",
        file=stream,
    )
    print("FOLLOW-UP SUMMARY", file=stream)
    print(f"status: {summary.follow_up.status}", file=stream)
    print(
        "safe_to_resume_reuse: "
        f"{str(summary.follow_up.safe_to_resume_reuse).lower()}",
        file=stream,
    )
    print(
        "total_candidate_rows: "
        f"{summary.follow_up.total_candidate_rows if summary.follow_up.total_candidate_rows is not None else 'n/a'}",
        file=stream,
    )
    print(f"total_extracted_rows: {summary.follow_up.total_extracted_rows}", file=stream)
    print(f"landed_batch_count: {summary.follow_up.landed_batch_count}", file=stream)
    print(
        "lower_bound_date_applied: "
        f"{summary.follow_up.lower_bound_date_applied or 'n/a'}",
        file=stream,
    )
    print(
        "partition_completion_marker_path: "
        f"{summary.follow_up.partition_completion_marker_path}",
        file=stream,
    )
    print(
        "partition_progress_path: "
        f"{summary.follow_up.partition_progress_path}",
        file=stream,
    )
    print("SUCCESS SUMMARY", file=stream)
    print(f"  {summary.follow_up.success_summary}", file=stream)
    print("WARNING SUMMARY", file=stream)
    print(f"  {summary.follow_up.warning_summary or 'none'}", file=stream)
    print("FAILURE SUMMARY", file=stream)
    print(f"  {summary.follow_up.failure_summary or 'none'}", file=stream)
    print(
        "  failure_classification: "
        f"{summary.follow_up.failure_classification or 'none'}",
        file=stream,
    )
    if summary.follow_up.planner_verdict is not None:
        print(
            f"planner_verdict: {summary.follow_up.planner_verdict}",
            file=stream,
        )
        print(
            f"planner_reason: {summary.follow_up.planner_reason or 'n/a'}",
            file=stream,
        )
        print(
            "recommended_partition_strategy: "
            f"{summary.follow_up.recommended_partition_strategy or 'n/a'}",
            file=stream,
        )
        print(
            "recommended_partition_count: "
            f"{summary.follow_up.recommended_partition_count if summary.follow_up.recommended_partition_count is not None else 'n/a'}",
            file=stream,
        )
        print(
            "observed_max_grouped_live_window_span_days: "
            f"{summary.follow_up.observed_max_grouped_live_window_span_days if summary.follow_up.observed_max_grouped_live_window_span_days is not None else 'n/a'}",
            file=stream,
        )
        print(
            "observed_max_live_promo_days: "
            f"{summary.follow_up.observed_max_live_promo_days if summary.follow_up.observed_max_live_promo_days is not None else 'n/a'}",
            file=stream,
        )
        print(
            "theoretical_completed_window_span_days_max: "
            f"{summary.follow_up.theoretical_completed_window_span_days_max if summary.follow_up.theoretical_completed_window_span_days_max is not None else 'n/a'}",
            file=stream,
        )
        print(
            "preflight_summary_json_path: "
            f"{summary.follow_up.preflight_summary_json_path or 'n/a'}",
            file=stream,
        )
        print(
            "rendered_preflight_sql_path: "
            f"{summary.follow_up.rendered_preflight_sql_path or 'n/a'}",
            file=stream,
        )
        print(
            f"note: {summary.follow_up.note or 'n/a'}",
            file=stream,
        )
    print("PER-STAGE SUMMARY", file=stream)
    for stage in summary.follow_up.per_stage:
        print(f"  stage_name: {stage.stage_name}", file=stream)
        print(
            "    elapsed_seconds: "
            f"{stage.elapsed_seconds if stage.elapsed_seconds is not None else 'n/a'}",
            file=stream,
        )
        print(f"    rows_written: {stage.rows_written}", file=stream)
        print(
            f"    rendered_sql_paths: {json.dumps(list(stage.rendered_sql_paths), sort_keys=True)}",
            file=stream,
        )
        print(
            f"    telemetry_paths: {json.dumps(list(stage.telemetry_paths), sort_keys=True)}",
            file=stream,
        )
        print(
            f"    diagnostics_paths: {json.dumps(list(stage.diagnostics_paths), sort_keys=True)}",
            file=stream,
        )
        print(
            "    completion_marker_paths: "
            f"{json.dumps(list(stage.completion_marker_paths), sort_keys=True)}",
            file=stream,
        )
    print(f"records: {len(summary.records)}", file=stream)
    for index, record in enumerate(summary.records, start=1):
        print(f"record[{index}]", file=stream)
        for key, value in record.to_dict().items():
            print(f"  {key}: {value if value is not None else 'n/a'}", file=stream)


def _accumulate_stage_summary(
    *,
    stage_accumulators: dict[str, dict[str, object]],
    stage_name: str,
    elapsed_seconds: float | None,
    rows_written: int | None,
    rendered_sql_path: str | None,
    telemetry_path: str | None,
    diagnostics_path: str | None,
    completion_marker_path: str | None,
) -> None:
    accumulator = stage_accumulators.setdefault(
        stage_name,
        {
            "elapsed_seconds": 0.0,
            "rows_written": 0,
            "rendered_sql_paths": set(),
            "telemetry_paths": set(),
            "diagnostics_paths": set(),
            "completion_marker_paths": set(),
        },
    )
    if elapsed_seconds is not None:
        accumulator["elapsed_seconds"] = float(accumulator["elapsed_seconds"]) + elapsed_seconds
    if rows_written is not None:
        accumulator["rows_written"] = int(accumulator["rows_written"]) + rows_written
    if rendered_sql_path:
        accumulator["rendered_sql_paths"].add(rendered_sql_path)
    if telemetry_path:
        accumulator["telemetry_paths"].add(telemetry_path)
    if diagnostics_path:
        accumulator["diagnostics_paths"].add(diagnostics_path)
    if completion_marker_path:
        accumulator["completion_marker_paths"].add(completion_marker_path)


def _build_preflight_rejected_summary_if_available(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    partition_index: int | None,
    partition_count: int | None,
) -> PromotionCompletedStage3ValidationSummary | None:
    preflight_summary_path = artifact_paths.extraction_preflight_summary_json_path(run_id)
    if not preflight_summary_path.exists():
        return None
    preflight_summary = _load_json(preflight_summary_path)
    planner_verdict = _as_str(preflight_summary.get("verdict"))
    if planner_verdict in (None, "SAFE_TO_EXTRACT"):
        return None
    effective_partition_index = partition_index
    effective_partition_count = partition_count
    if effective_partition_index is None:
        effective_partition_index = _as_int(preflight_summary.get("partition_index"))
    if effective_partition_count is None:
        effective_partition_count = _as_int(preflight_summary.get("partition_count"))
    lower_bound_date_applied = _as_str(
        preflight_summary.get("rendered_query_parameter_summary", {}).get(
            "completed_sales_history_start_date"
        )
    ) or _as_str(
        preflight_summary.get("estimated_window_summary", {}).get(
            "completed_sales_history_start_date"
        )
    )
    partition_progress_path = artifact_paths.extraction_partition_progress_path(run_id)
    partition_completion_marker_path = artifact_paths.extraction_partition_completion_path(run_id)
    follow_up = PromotionCompletedStage3FollowUpSummary(
        partition_index=effective_partition_index,
        partition_count=effective_partition_count,
        total_candidate_rows=_as_int(preflight_summary.get("candidate_promotion_row_count")),
        total_extracted_rows=0,
        landed_batch_count=0,
        lower_bound_date_applied=lower_bound_date_applied,
        partition_completion_marker_path=str(partition_completion_marker_path),
        partition_progress_path=str(partition_progress_path),
        per_stage=(),
        safe_to_resume_reuse=False,
        status="preflight_rejected_before_stage3",
        success_summary=(
            "Stage 3 extraction did not start because preflight rejected the requested partition."
        ),
        warning_summary=None,
        failure_summary="Stage 3 extraction artifacts do not exist because preflight stopped the run.",
        failure_classification="SQL planning problem",
        planner_verdict=planner_verdict,
        planner_reason=_as_str(preflight_summary.get("reason")),
        recommended_partition_strategy=_as_str(preflight_summary.get("recommended_partition_strategy")),
        recommended_partition_count=_as_int(preflight_summary.get("recommended_partition_count")),
        observed_max_grouped_live_window_span_days=_as_int(
            preflight_summary.get("observed_max_grouped_live_window_span_days")
        ),
        observed_max_live_promo_days=_as_int(preflight_summary.get("observed_max_live_promo_days")),
        theoretical_completed_window_span_days_max=_as_int(
            preflight_summary.get("theoretical_completed_window_span_days_max")
        ),
        preflight_summary_json_path=str(preflight_summary_path),
        rendered_preflight_sql_path=str(artifact_paths.rendered_preflight_sql_path(run_id)),
        note="No Stage 3 extraction artifacts exist yet because preflight rejected the run before extraction started.",
    )
    return PromotionCompletedStage3ValidationSummary(
        run_id=run_id,
        partition_index=effective_partition_index,
        partition_count=effective_partition_count,
        completed_sales_history_start_date=lower_bound_date_applied,
        records=(),
        follow_up=follow_up,
    )


def _collect_failure_signal_from_payload(payload: dict[str, Any], failure_signals: list[str]) -> None:
    failure_message = _as_str(payload.get("failure_message"))
    failure_stage = _as_str(payload.get("failure_stage"))
    current_sql_subphase = _as_str(payload.get("current_sql_subphase"))
    extraction_status = _as_str(payload.get("extraction_status"))
    status_is_failure = extraction_status is not None and extraction_status.lower() in {
        "failed",
        "error",
    }
    if failure_message:
        failure_signals.append(failure_message)
    if failure_stage and (status_is_failure or failure_message):
        failure_signals.append(failure_stage)
    if current_sql_subphase and (status_is_failure or failure_message):
        failure_signals.append(current_sql_subphase)
    if status_is_failure:
        failure_signals.append(extraction_status)


def _classify_failure_signals(
    failure_signals: list[str],
    *,
    partition_completion_state: str | None,
    completion_state: str | None,
    has_partition_completion: bool,
) -> str | None:
    classification_text = " ".join(failure_signals).lower()
    if (
        not has_partition_completion
        or partition_completion_state not in (None, "finalized")
        or completion_state not in (None, "finalized")
    ):
        return "resume / completion-marker inconsistency"
    if not classification_text:
        return None
    if (
        "completion marker" in classification_text
        or "resume" in classification_text
        or "checksum mismatch" in classification_text
        or "row count mismatch" in classification_text
    ):
        return "resume / completion-marker inconsistency"
    if (
        "query render" in classification_text
        or "planning" in classification_text
        or "candidate promotion row count probe" in classification_text
    ):
        return "SQL planning problem"
    if "source sku identity" in classification_text or "advice-source sku identity" in classification_text:
        return "advice-source identity problem"
    if "execut" in classification_text:
        return "SQL execution problem"
    if "fetch" in classification_text or "transfer" in classification_text:
        return "SQL fetch / transfer problem"
    if (
        "writing extracted parquet" in classification_text
        or "normalizing extracted promotion frame" in classification_text
        or "combining finalized landed batch artifacts" in classification_text
        or "assembler" in classification_text
        or "artifact" in classification_text
    ):
        return "artifact assembly problem"
    return "artifact assembly problem"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Print a staged completed-extraction validation summary for one completed partition run id."
        )
    )
    parser.add_argument("--env-file")
    parser.add_argument("--artifact-root")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--partition-index", type=int)
    parser.add_argument("--partition-count", type=int)
    parser.add_argument("--json", action="store_true")
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json(path)


def _derive_run_id_from_path(path: Path) -> str:
    return path.parent.name


def _parse_batch_number(run_id: str) -> int | None:
    match = _BATCH_RUN_ID_PATTERN.search(run_id)
    if match is None:
        return None
    return int(match.group(1))


def _resolve_row_window(*, batch_number: int | None, batch_row_count: int | None) -> tuple[int | None, int | None]:
    if batch_number is None or batch_row_count is None or batch_row_count < 1:
        return (None, None)
    row_start = ((batch_number - 1) * batch_row_count) + 1
    row_end = batch_number * batch_row_count
    return (row_start, row_end)


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


if __name__ == "__main__":
    main()
