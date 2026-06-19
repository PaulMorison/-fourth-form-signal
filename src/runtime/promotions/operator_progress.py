from __future__ import annotations

"""Operator-facing progress and failure traces for promotions runtime runs."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import csv
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from threading import Event, Lock, Thread, current_thread
import time
import logging
import warnings
from typing import Literal, Sequence, TextIO

import pandas as pd

from data.promotions.mssql_query_executor import (
    PromotionMssqlConnectionError,
    PromotionMssqlConnectionTimeoutError,
    PromotionMssqlQueryError,
    PromotionMssqlQueryTimeoutError,
)
from runtime.promotions.config import (
    DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS,
    DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS,
    PromotionArtifactPaths,
    PromotionMssqlSettingsSummary,
)


@dataclass(frozen=True)
class PromotionOperatorStageRecord:
    stage_number: int
    total_stages: int
    stage_name: str
    status: str
    started_at_utc: str
    completed_at_utc: str | None
    elapsed_seconds: float | None
    row_count: int | None
    file_count: int | None
    output_paths: tuple[str, ...]
    note: str | None
    owner: str | None = None
    reason: str | None = None
    action: str | None = None
    exception_type: str | None = None
    sql_subphase: str | None = None
    failure_artifact_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionOperatorProgressArtifacts:
    status: str
    log_path: str
    summary_path: str
    summary_csv_path: str
    stage_timings_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


OperatorDisplayMode = Literal["verbose", "operator"]


def resolve_operator_display_mode(
    *,
    requested_mode: str | None = None,
) -> OperatorDisplayMode:
    """Resolve terminal display mode from CLI override or environment."""

    candidate = (requested_mode or os.getenv("PROMOTIONS_OPERATOR_DISPLAY", "verbose")).strip().lower()
    if candidate in {"operator", "summary", "human"}:
        return "operator"
    return "verbose"


def configure_operator_console_quiet() -> None:
    """Reduce engineering noise when operator display mode is active."""

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s", force=True)
    warnings.filterwarnings("ignore", category=FutureWarning)
    try:
        from pandas.errors import PerformanceWarning

        warnings.filterwarnings("ignore", category=PerformanceWarning)
    except Exception:
        pass


class PromotionOperatorProgress:
    """Emit clean operator progress to stdout and persist durable run traces."""

    def __init__(
        self,
        *,
        run_id: str,
        artifact_paths: PromotionArtifactPaths,
        stream: TextIO | None = None,
        display_mode: OperatorDisplayMode | str = "verbose",
    ) -> None:
        self._run_id = run_id
        self._artifact_paths = artifact_paths
        self._stream = stream or sys.stdout
        resolved_mode = str(display_mode).strip().lower()
        self._display_mode: OperatorDisplayMode = (
            "operator" if resolved_mode in {"operator", "summary", "human"} else "verbose"
        )
        self._lines: list[str] = []
        self._stage_records: list[PromotionOperatorStageRecord] = []
        self._active_stage: dict[str, object] | None = None
        self._started_at_utc: str | None = None
        self._completed_at_utc: str | None = None
        self._run_context: dict[str, str] = {}
        self._heartbeat_lock = Lock()
        self._heartbeat_state: dict[str, object] | None = None
        self._heartbeat_stop_event: Event | None = None
        self._heartbeat_thread: Thread | None = None
        self._last_heartbeat_emit_perf: float | None = None

    def start_run(
        self,
        *,
        as_of_date: str,
        artifact_root: str | Path,
        local_inspection_root: str | Path | None = None,
        server: str,
        database: str,
        execution_mode: str = "live_sql",
        connect_timeout_seconds: int | None = None,
        connect_retry_attempts: int = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS,
        connect_retry_backoff_seconds: float = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS,
        query_timeout_seconds: int | None = None,
        partition_strategy: str | None = None,
        partition_count: int | None = None,
        auto_repartition_completed: bool = True,
        max_completed_repartition_attempts: int = 3,
        max_completed_partition_count: int = 512,
        enable_landed_batches: bool = True,
        batch_row_count: int | None = None,
        completed_sales_history_start_date: str | None = None,
        enable_chunked_fetch: bool = True,
        chunk_row_count: int | None = None,
        resume_completed_partitions: bool = True,
        stage_temp_chunk_files: bool = True,
        sql_settings_summary: PromotionMssqlSettingsSummary | None = None,
    ) -> None:
        self._started_at_utc = datetime.now(tz=UTC).isoformat()
        self._run_context = {
            "as_of_date": as_of_date,
            "artifact_root": str(artifact_root),
            "local_inspection_root": str(local_inspection_root) if local_inspection_root is not None else "disabled",
            "server": server,
            "database": database,
            "execution_mode": execution_mode,
            "connect_timeout_seconds": (
                str(connect_timeout_seconds) if connect_timeout_seconds is not None else "disabled"
            ),
            "connect_retry_attempts": str(connect_retry_attempts),
            "connect_retry_backoff_seconds": str(connect_retry_backoff_seconds),
            "query_timeout_seconds": (
                str(query_timeout_seconds) if query_timeout_seconds is not None else "disabled"
            ),
            "partition_strategy": partition_strategy or "disabled",
            "partition_count": str(partition_count) if partition_count is not None else "disabled",
            "auto_repartition_completed": str(auto_repartition_completed).lower(),
            "max_completed_repartition_attempts": str(max_completed_repartition_attempts),
            "max_completed_partition_count": str(max_completed_partition_count),
            "enable_landed_batches": str(enable_landed_batches).lower(),
            "batch_row_count": str(batch_row_count) if batch_row_count is not None else "disabled",
            "completed_sales_history_start_date": (
                completed_sales_history_start_date or "disabled"
            ),
            "enable_chunked_fetch": str(enable_chunked_fetch).lower(),
            "chunk_row_count": str(chunk_row_count) if chunk_row_count is not None else "disabled",
            "resume_completed_partitions": str(resume_completed_partitions).lower(),
            "stage_temp_chunk_files": str(stage_temp_chunk_files).lower(),
        }
        if sql_settings_summary is not None:
            self._run_context.update(sql_settings_summary.to_context_dict())
        if self._display_mode == "operator":
            self._emit("")
            self._emit("=" * 72)
            self._emit(f"  PROMOTIONS RUN · {self._run_id}")
            self._emit(
                f"  As of {as_of_date}  |  Mode {execution_mode}  |  DB {database}"
            )
            self._emit(f"  Outputs {artifact_root}")
            self._emit("=" * 72)
            self._emit("")
            return

        self._emit("PROMOTIONS OPERATIONAL CYCLE")
        self._emit(f"run_id: {self._run_id}")
        self._emit(f"execution_mode: {execution_mode}")
        self._emit(f"mode: {execution_mode}")
        self._emit(f"as_of_date: {as_of_date}")
        self._emit(f"artifact_root: {artifact_root}")
        self._emit(
            f"local_inspection_root: {local_inspection_root if local_inspection_root is not None else 'disabled'}"
        )
        if sql_settings_summary is not None:
            for line in sql_settings_summary.render_lines():
                self._emit(line)
        else:
            self._emit(
                "connect_timeout_seconds: "
                f"{connect_timeout_seconds if connect_timeout_seconds is not None else 'disabled'}"
            )
            self._emit(f"connect_retry_attempts: {connect_retry_attempts}")
            self._emit(f"connect_retry_backoff_seconds: {connect_retry_backoff_seconds}")
            self._emit(
                "query_timeout_seconds: "
                f"{query_timeout_seconds if query_timeout_seconds is not None else 'disabled'}"
            )
            self._emit(f"mssql: {server}/{database}")
        self._emit(f"partition_strategy: {partition_strategy or 'disabled'}")
        self._emit(
            f"partition_count: {partition_count if partition_count is not None else 'disabled'}"
        )
        self._emit(f"auto_repartition_completed: {str(auto_repartition_completed).lower()}")
        self._emit(
            f"max_completed_repartition_attempts: {max_completed_repartition_attempts}"
        )
        self._emit(f"max_completed_partition_count: {max_completed_partition_count}")
        self._emit(f"enable_landed_batches: {str(enable_landed_batches).lower()}")
        self._emit(
            f"batch_row_count: {batch_row_count if batch_row_count is not None else 'disabled'}"
        )
        self._emit(
            "completed_sales_history_start_date: "
            f"{completed_sales_history_start_date or 'disabled'}"
        )
        self._emit(f"enable_chunked_fetch: {str(enable_chunked_fetch).lower()}")
        self._emit(
            f"chunk_row_count: {chunk_row_count if chunk_row_count is not None else 'disabled'}"
        )
        self._emit(
            f"resume_completed_partitions: {str(resume_completed_partitions).lower()}"
        )
        self._emit(f"stage_temp_chunk_files: {str(stage_temp_chunk_files).lower()}")
        self._emit(f"operator_summary_json: {self._artifact_paths.operator_summary_path(self._run_id)}")
        self._emit(f"operator_summary_csv: {self._artifact_paths.operator_summary_csv_path(self._run_id)}")
        self._emit(f"operator_stage_timings_csv: {self._artifact_paths.operator_stage_timings_path(self._run_id)}")

    def start_stage(self, stage_number: int, total_stages: int, stage_name: str) -> None:
        if self._active_stage is not None:
            raise RuntimeError("Cannot start a new operator stage while another stage is active.")
        started_at_utc = datetime.now(tz=UTC).isoformat()
        self._active_stage = {
            "stage_number": int(stage_number),
            "total_stages": int(total_stages),
            "stage_name": stage_name,
            "started_at_utc": started_at_utc,
            "started_at_perf": time.perf_counter(),
        }
        self._emit("")
        if self._display_mode == "operator":
            self._emit(f"[{stage_number:>2}/{total_stages}] {stage_name}")
            return
        self._emit(f"START STAGE {stage_number}/{total_stages}: {stage_name}")
        self._emit(f"  run_id: {self._run_id}")

    def detail(self, message: str) -> None:
        if self._display_mode == "operator":
            self._log_only(f"  {message}")
            return
        self._emit(f"  {message}")

    def update_heartbeat(
        self,
        *,
        subtask: str | None = None,
        row_count: int | None = None,
        file_count: int | None = None,
        emit_now: bool = False,
    ) -> None:
        with self._heartbeat_lock:
            if self._heartbeat_state is None:
                return
            if subtask is not None:
                self._heartbeat_state["subtask"] = subtask
            if row_count is not None:
                self._heartbeat_state["row_count"] = row_count
            if file_count is not None:
                self._heartbeat_state["file_count"] = file_count
            snapshot = dict(self._heartbeat_state)
        if emit_now:
            self._emit_heartbeat(snapshot)

    @contextmanager
    def heartbeat(
        self,
        subtask: str,
        *,
        heartbeat_seconds: float = 10.0,
        row_count: int | None = None,
        file_count: int | None = None,
    ):
        self.start_heartbeat(
            subtask=subtask,
            heartbeat_seconds=heartbeat_seconds,
            row_count=row_count,
            file_count=file_count,
        )
        try:
            yield self
        finally:
            self.stop_heartbeat()

    def start_heartbeat(
        self,
        *,
        subtask: str,
        heartbeat_seconds: float = 10.0,
        row_count: int | None = None,
        file_count: int | None = None,
    ) -> None:
        active_stage = self._require_active_stage()
        self.stop_heartbeat()
        stop_event = Event()
        with self._heartbeat_lock:
            self._heartbeat_state = {
                "subtask": subtask,
                "row_count": row_count,
                "file_count": file_count,
                "stage_number": int(active_stage["stage_number"]),
                "total_stages": int(active_stage["total_stages"]),
                "stage_name": str(active_stage["stage_name"]),
            }
        self._heartbeat_stop_event = stop_event

        def _runner() -> None:
            while not stop_event.wait(heartbeat_seconds):
                with self._heartbeat_lock:
                    snapshot = dict(self._heartbeat_state or {})
                if not snapshot or self._active_stage is None:
                    return
                self._emit_heartbeat(snapshot)

        self._heartbeat_thread = Thread(
            target=_runner,
            name=f"promotions-heartbeat-{self._run_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        stop_event = self._heartbeat_stop_event
        thread = self._heartbeat_thread
        self._heartbeat_stop_event = None
        self._heartbeat_thread = None
        with self._heartbeat_lock:
            self._heartbeat_state = None
        if stop_event is not None:
            stop_event.set()
        if thread is not None and thread.is_alive() and thread is not current_thread():
            thread.join(timeout=0.2)

    def complete_stage(
        self,
        *,
        row_count: int | None = None,
        file_count: int | None = None,
        output_paths: Sequence[str | Path] | None = None,
        note: str | None = None,
    ) -> PromotionOperatorStageRecord:
        active_stage = self._require_active_stage()
        self.stop_heartbeat()
        completed_at_utc = datetime.now(tz=UTC).isoformat()
        elapsed_seconds = time.perf_counter() - float(active_stage["started_at_perf"])
        normalized_outputs = tuple(str(path) for path in (output_paths or ()))
        record = PromotionOperatorStageRecord(
            stage_number=int(active_stage["stage_number"]),
            total_stages=int(active_stage["total_stages"]),
            stage_name=str(active_stage["stage_name"]),
            status="completed",
            started_at_utc=str(active_stage["started_at_utc"]),
            completed_at_utc=completed_at_utc,
            elapsed_seconds=round(elapsed_seconds, 3),
            row_count=row_count,
            file_count=file_count,
            output_paths=normalized_outputs,
            note=note,
        )
        self._stage_records.append(record)
        if self._display_mode == "operator":
            summary_parts = [f"        ✓ Done in {_format_duration(record.elapsed_seconds)}"]
            if row_count is not None:
                summary_parts.append(f"{_format_integer(row_count)} rows")
            if file_count is not None:
                summary_parts.append(f"{_format_integer(file_count)} files")
            self._emit(" · ".join(summary_parts))
            if note:
                self._log_only(f"        note: {note}")
            self._emit("")
        else:
            self._emit(f"FINISH STAGE {record.stage_number}/{record.total_stages}: {record.stage_name}")
            if row_count is not None:
                self._emit(f"  rows: {row_count}")
            if file_count is not None:
                self._emit(f"  files: {file_count}")
            for index, output_path in enumerate(normalized_outputs, start=1):
                self._emit(f"  output_path[{index}/{len(normalized_outputs)}]: {output_path}")
            if note:
                self._emit(f"  note: {note}")
            self._emit(f"  elapsed: {record.elapsed_seconds:.3f}s")
        self._active_stage = None
        return record

    def fail(self, error: BaseException) -> PromotionOperatorStageRecord:
        active_stage = self._require_active_stage()
        self.stop_heartbeat()
        completed_at_utc = datetime.now(tz=UTC).isoformat()
        elapsed_seconds = time.perf_counter() - float(active_stage["started_at_perf"])
        owner, reason, action = classify_operator_failure(error)
        sql_subphase = _extract_error_attr(error, "current_sql_subphase")
        failure_artifact_paths = _collect_failure_artifact_paths(error)
        record = PromotionOperatorStageRecord(
            stage_number=int(active_stage["stage_number"]),
            total_stages=int(active_stage["total_stages"]),
            stage_name=str(active_stage["stage_name"]),
            status="failed",
            started_at_utc=str(active_stage["started_at_utc"]),
            completed_at_utc=completed_at_utc,
            elapsed_seconds=round(elapsed_seconds, 3),
            row_count=None,
            file_count=None,
            output_paths=(),
            note=None,
            owner=owner,
            reason=reason,
            action=action,
            exception_type=type(error).__name__,
            sql_subphase=sql_subphase,
            failure_artifact_paths=failure_artifact_paths,
        )
        self._stage_records.append(record)
        self._emit("")
        if self._display_mode == "operator":
            self._emit("!" * 72)
            self._emit(
                f"  FAILED at stage {record.stage_number}/{record.total_stages}: {record.stage_name}"
            )
            self._emit(f"  Reason: {reason}")
            self._emit(f"  Next step: {action}")
            self._emit(f"  Elapsed: {_format_duration(record.elapsed_seconds)}")
            self._emit("!" * 72)
            self._log_only(f"  exception_type: {record.exception_type}")
            self._log_only(f"  subphase: {record.sql_subphase or 'unavailable'}")
            self._log_only(f"  owner: {owner}")
            for label, path in _iter_failure_artifact_labels(error):
                self._log_only(f"  {label}_path: {path}")
            self._log_only(f"  operator_log_path: {self._artifact_paths.operator_log_path(self._run_id)}")
            self._log_only(f"  manifest_root: {self._artifact_paths.manifests_run_root(self._run_id)}")
        else:
            self._emit("FAILED STAGE")
            self._emit(f"  stage: {record.stage_number}/{record.total_stages} {record.stage_name}")
            self._emit(f"  exception_type: {record.exception_type}")
            self._emit(f"  subphase: {record.sql_subphase or 'unavailable'}")
            self._emit(f"  owner: {owner}")
            self._emit(f"  reason: {reason}")
            self._emit(f"  next_action: {action}")
            for label, path in _iter_failure_artifact_labels(error):
                self._emit(f"  {label}_path: {path}")
            self._emit(f"  operator_log_path: {self._artifact_paths.operator_log_path(self._run_id)}")
            self._emit(f"  operator_summary_json_path: {self._artifact_paths.operator_summary_path(self._run_id)}")
            self._emit(f"  operator_summary_csv_path: {self._artifact_paths.operator_summary_csv_path(self._run_id)}")
            self._emit(f"  manifest_root: {self._artifact_paths.manifests_run_root(self._run_id)}")
            self._emit(f"  elapsed: {record.elapsed_seconds:.3f}s")
        self._active_stage = None
        return record

    def emit_final_outputs(
        self,
        *,
        outputs: dict[str, str],
    ) -> None:
        if self._display_mode == "operator":
            self._emit("")
            self._emit("-" * 72)
            self._emit("  KEY OUTPUTS")
            priority_keys = (
                "store_prediction_download_path",
                "nas_store_prediction_download_path",
                "inspection_review_packet_csv_path",
                "operational_cycle_manifest_path",
                "operator_summary_json_path",
                "local_inspection_csv_path",
            )
            emitted: set[str] = set()
            for key in priority_keys:
                path = outputs.get(key)
                if path and path not in {"unavailable", "not_generated"}:
                    self._emit(f"  {key}: {path}")
                    emitted.add(key)
            for key, path in sorted(outputs.items()):
                if key in emitted or path in {"unavailable", "not_generated", "none"}:
                    continue
                if key.endswith("_path") and "stage6" not in key and "completed_rendered" not in key:
                    self._log_only(f"  {key}: {path}")
            self._emit("-" * 72)
            return

        self._emit("")
        self._emit("FINAL OUTPUTS")
        for label, path in outputs.items():
            self._emit(f"  {label}: {path}")

    def emit_run_summary(self) -> None:
        if self._display_mode != "operator" or not self._stage_records:
            return
        self._emit("")
        self._emit("-" * 72)
        self._emit("  RUN SUMMARY")
        self._emit("-" * 72)
        self._emit(f"  {'Stage':<42} {'Time':>8}  {'Rows':>10}")
        total_elapsed = 0.0
        for record in self._stage_records:
            if record.status != "completed":
                continue
            elapsed = float(record.elapsed_seconds or 0.0)
            total_elapsed += elapsed
            rows = _format_integer(record.row_count) if record.row_count is not None else "—"
            self._emit(
                f"  {record.stage_name[:42]:<42} {_format_duration(elapsed):>8}  {rows:>10}"
            )
        self._emit(f"  {'TOTAL':<42} {_format_duration(total_elapsed):>8}")
        self._emit("-" * 72)

    def emit_order_preview(self, *, store_prediction_csv_path: str | Path, limit: int = 20) -> None:
        if self._display_mode != "operator":
            return
        csv_path = Path(store_prediction_csv_path)
        if not csv_path.exists():
            self._emit("")
            self._emit("  ORDER PREVIEW: store prediction CSV not available.")
            return
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
        if frame.empty:
            self._emit("")
            self._emit("  ORDER PREVIEW: no rows in store prediction CSV.")
            return

        preview_columns = [
            column
            for column in (
                "store_number",
                "sku_number",
                "sku_description",
                "operator_action",
                "order_units",
                "expected_promo_demand",
                "current_soh",
                "projected_stock_gap_units",
                "reason_short",
                "review_flag",
            )
            if column in frame.columns
        ]
        if not preview_columns:
            preview_columns = list(frame.columns[:8])

        order_frame = frame.copy()
        if "order_units" in order_frame.columns:
            order_units = pd.to_numeric(order_frame["order_units"], errors="coerce").fillna(0)
            order_frame = order_frame.loc[order_units.gt(0)].copy()
        if order_frame.empty:
            order_frame = frame.head(limit)
        else:
            order_frame = order_frame.head(limit)

        self._emit("")
        self._emit("-" * 72)
        self._emit(f"  ORDER RECOMMENDATIONS (showing {len(order_frame)} of {len(frame)} rows)")
        self._emit("-" * 72)
        header = "  " + " | ".join(f"{column:>16}" for column in preview_columns[:6])
        self._emit(header)
        self._emit("  " + "-" * (len(header) - 2))
        for _, row in order_frame.iterrows():
            values = []
            for column in preview_columns[:6]:
                text = str(row.get(column, "")).strip().replace("\n", " ")
                if len(text) > 16:
                    text = text[:15] + "…"
                values.append(f"{text:>16}")
            self._emit("  " + " | ".join(values))
        self._emit("-" * 72)
        self._emit(f"  Full review file: {csv_path}")

    def persist(
        self,
        *,
        status: str,
        final_outputs: dict[str, str] | None = None,
    ) -> PromotionOperatorProgressArtifacts:
        self._completed_at_utc = datetime.now(tz=UTC).isoformat()
        log_path = self._artifact_paths.operator_log_path(self._run_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(self._lines) + "\n", encoding="utf-8")

        stage_timings_path = self._artifact_paths.operator_stage_timings_path(self._run_id)
        stage_timings_path.parent.mkdir(parents=True, exist_ok=True)
        with stage_timings_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "stage_number",
                    "total_stages",
                    "stage_name",
                    "status",
                    "started_at_utc",
                    "completed_at_utc",
                    "elapsed_seconds",
                    "row_count",
                    "file_count",
                    "owner",
                    "reason",
                    "action",
                    "exception_type",
                    "sql_subphase",
                    "failure_artifact_paths",
                    "output_paths",
                    "note",
                ),
            )
            writer.writeheader()
            for record in self._stage_records:
                writer.writerow(
                    {
                        **record.to_dict(),
                        "failure_artifact_paths": " | ".join(record.failure_artifact_paths),
                        "output_paths": " | ".join(record.output_paths),
                    }
                )

        summary_path = self._artifact_paths.operator_summary_path(self._run_id)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_payload = {
            "run_id": self._run_id,
            "status": status,
            "started_at_utc": self._started_at_utc,
            "completed_at_utc": self._completed_at_utc,
            "elapsed_seconds": self._elapsed_seconds(),
            "context": self._run_context,
            "log_path": str(log_path),
            "stage_timings_path": str(stage_timings_path),
            "final_outputs": final_outputs or {},
            "stages": [record.to_dict() for record in self._stage_records],
        }
        summary_path.write_text(
            json.dumps(summary_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        summary_csv_path = self._artifact_paths.operator_summary_csv_path(self._run_id)
        summary_csv_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "run_id",
                    "status",
                    "started_at_utc",
                    "completed_at_utc",
                    "elapsed_seconds",
                    "execution_mode",
                    "as_of_date",
                    "artifact_root",
                    "local_inspection_root",
                    "server",
                    "database",
                    "connect_timeout_seconds",
                    "connect_retry_attempts",
                    "connect_retry_backoff_seconds",
                    "query_timeout_seconds",
                    "partition_strategy",
                    "partition_count",
                    "auto_repartition_completed",
                    "max_completed_repartition_attempts",
                    "max_completed_partition_count",
                    "log_path",
                    "summary_path",
                    "stage_timings_path",
                    "final_output_keys",
                ),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "run_id": self._run_id,
                    "status": status,
                    "started_at_utc": self._started_at_utc,
                    "completed_at_utc": self._completed_at_utc,
                    "elapsed_seconds": self._elapsed_seconds(),
                    "execution_mode": self._run_context.get("execution_mode"),
                    "as_of_date": self._run_context.get("as_of_date"),
                    "artifact_root": self._run_context.get("artifact_root"),
                    "local_inspection_root": self._run_context.get("local_inspection_root"),
                    "server": self._run_context.get("server"),
                    "database": self._run_context.get("database"),
                    "connect_timeout_seconds": self._run_context.get("connect_timeout_seconds"),
                    "connect_retry_attempts": self._run_context.get("connect_retry_attempts"),
                    "connect_retry_backoff_seconds": self._run_context.get(
                        "connect_retry_backoff_seconds"
                    ),
                    "query_timeout_seconds": self._run_context.get("query_timeout_seconds"),
                    "partition_strategy": self._run_context.get("partition_strategy"),
                    "partition_count": self._run_context.get("partition_count"),
                    "auto_repartition_completed": self._run_context.get("auto_repartition_completed"),
                    "max_completed_repartition_attempts": self._run_context.get(
                        "max_completed_repartition_attempts"
                    ),
                    "max_completed_partition_count": self._run_context.get(
                        "max_completed_partition_count"
                    ),
                    "log_path": str(log_path),
                    "summary_path": str(summary_path),
                    "stage_timings_path": str(stage_timings_path),
                    "final_output_keys": " | ".join(sorted((final_outputs or {}).keys())),
                }
            )
        return PromotionOperatorProgressArtifacts(
            status=status,
            log_path=str(log_path),
            summary_path=str(summary_path),
            summary_csv_path=str(summary_csv_path),
            stage_timings_path=str(stage_timings_path),
        )

    def finalize_operator_view(
        self,
        *,
        status: str,
        store_prediction_csv_path: str | Path | None = None,
    ) -> None:
        if self._display_mode != "operator":
            return
        self.emit_run_summary()
        if store_prediction_csv_path is not None:
            self.emit_order_preview(store_prediction_csv_path=store_prediction_csv_path)
        self._emit("")
        if status == "completed":
            self._emit("  ✓ Promotions run completed successfully.")
        else:
            self._emit(f"  Run finished with status: {status}")
        self._emit("")

    @property
    def has_active_stage(self) -> bool:
        return self._active_stage is not None

    def _elapsed_seconds(self) -> float | None:
        if not self._started_at_utc or not self._completed_at_utc:
            return None
        started_at = datetime.fromisoformat(self._started_at_utc)
        completed_at = datetime.fromisoformat(self._completed_at_utc)
        return round((completed_at - started_at).total_seconds(), 3)

    def _emit(self, message: str) -> None:
        self._lines.append(message)
        print(message, file=self._stream, flush=True)

    def _log_only(self, message: str) -> None:
        self._lines.append(message)

    def _emit_heartbeat(self, snapshot: dict[str, object]) -> None:
        active_stage = self._active_stage
        if active_stage is None:
            return
        elapsed_seconds = time.perf_counter() - float(active_stage["started_at_perf"])
        if self._display_mode == "operator":
            now_perf = time.perf_counter()
            if (
                self._last_heartbeat_emit_perf is not None
                and (now_perf - self._last_heartbeat_emit_perf) < 8.0
            ):
                return
            self._last_heartbeat_emit_perf = now_perf
            parts = [
                "        … still running",
                _format_duration(elapsed_seconds),
                str(snapshot.get("subtask", "")).strip(),
            ]
            row_count = snapshot.get("row_count")
            if row_count is not None:
                parts.append(f"{_format_integer(int(row_count))} rows")
            self._emit(" · ".join(part for part in parts if part))
            self._log_only(
                " | ".join(
                    [
                        f"HEARTBEAT STAGE {snapshot.get('stage_number')}/{snapshot.get('total_stages')}",
                        str(snapshot.get("stage_name")),
                        f"subphase: {snapshot.get('subtask', '')}",
                        f"elapsed_seconds: {elapsed_seconds:.1f}",
                        f"rows: {row_count}" if row_count is not None else "",
                    ]
                ).strip()
            )
            return
        parts = [
            f"  HEARTBEAT STAGE {snapshot.get('stage_number')}/{snapshot.get('total_stages')}",
            str(snapshot.get("stage_name")),
            f"subphase: {snapshot.get('subtask', '')}",
            f"elapsed_seconds: {elapsed_seconds:.1f}",
        ]
        row_count = snapshot.get("row_count")
        file_count = snapshot.get("file_count")
        if row_count is not None:
            parts.append(f"rows: {row_count}")
        if file_count is not None:
            parts.append(f"files: {file_count}")
        self._emit(" | ".join(parts))

    def _require_active_stage(self) -> dict[str, object]:
        if self._active_stage is None:
            raise RuntimeError("No active operator stage is available.")
        return self._active_stage


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total_seconds = max(float(seconds), 0.0)
    if total_seconds < 60.0:
        return f"{total_seconds:.1f}s"
    minutes = int(total_seconds // 60)
    remainder = int(round(total_seconds % 60))
    if remainder == 60:
        minutes += 1
        remainder = 0
    return f"{minutes}m {remainder:02d}s"


def _format_integer(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


def classify_operator_failure(error: BaseException) -> tuple[str, str, str]:
    message = _normalize_error_message(error)
    if isinstance(error, KeyboardInterrupt) or bool(getattr(error, "stage3_interrupted", False)):
        return (
            "operator",
            message,
            "The run was interrupted by operator cancellation. Review the Stage 3 interruption diagnostics artifacts and rerun when ready.",
        )
    if isinstance(error, PromotionMssqlConnectionTimeoutError):
        return (
            "operator",
            message,
            "The run failed during SQL connect/login before execution started. Verify SQL Server network reachability, authentication latency, PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS, and the connect retry settings before rerunning.",
        )
    if isinstance(error, PromotionMssqlConnectionError):
        return (
            "operator",
            message,
            "The run failed during SQL connect/login before execution started. Check PROMOTIONS_MSSQL_* credentials, ODBC driver availability, and SQL Server network reachability before rerunning.",
        )
    if isinstance(error, PromotionMssqlQueryTimeoutError):
        return (
            "operator",
            message,
            "Inspect the SQL diagnostics summary, confirm the extraction is slow in SQL execution rather than connection setup, and either tune the source query plan or increase PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS before rerunning.",
        )
    if isinstance(error, PromotionMssqlQueryError):
        return (
            "operator",
            message,
            "Verify PROMOTIONS_SCHEMA, PROMOTIONS_ADVICE_TABLE, PROMOTIONS_PWLOGD_TABLE, and live source column compatibility before rerunning.",
        )
    if type(error).__name__ == "PromotionCompletedPreflightRejectedError":
        if getattr(error, "cost_guardrail_verdict", None) == "TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET":
            return (
                "operator",
                message,
                "Review the preflight cost_guardrail_reason, retry history, and rendered preflight SQL before rerunning; this completed-extraction slice was rejected as too expensive for the live timeout budget.",
            )
        return (
            "operator",
            message,
            "Review the completed partition retry history and the planner recommendation, then run the exact inspector command shown below before rerunning the live operational cycle.",
        )
    if isinstance(error, PermissionError):
        return (
            "operator",
            message,
            "Confirm the configured NAS root exists and is writable for cleaned_data, training, prediction, artefacts, logs, manifests, inspection, audit, operational_cycles, decision_surface, cohorts, models, datasets, scoring, and reports outputs.",
        )
    if isinstance(error, ValueError) and "PROMOTIONS_" in message:
        return (
            "operator",
            message,
            "Correct the promotions runtime configuration in the active .env or CLI overrides and rerun.",
        )
    return (
        "code",
        message,
        "Inspect the stage-specific stack trace and fix the runtime code path before rerunning this operational cycle.",
    )


def _normalize_error_message(error: BaseException) -> str:
    message = str(error).strip() or error.__class__.__name__
    return " ".join(message.split())


def _extract_error_attr(error: BaseException, attribute_name: str) -> str | None:
    value = getattr(error, attribute_name, None)
    if value is None:
        return None
    return str(value)


def _iter_failure_artifact_labels(error: BaseException) -> tuple[tuple[str, str], ...]:
    labeled_attrs = (
        ("extraction_telemetry_json_path", "extraction_telemetry"),
        ("extraction_telemetry_csv_path", "extraction_telemetry_csv"),
        ("sql_diagnostics_summary_json_path", "sql_diagnostics_summary"),
        ("sql_diagnostics_summary_txt_path", "sql_diagnostics_summary_txt"),
        ("completed_partition_summary_path", "completed_partition_summary"),
        ("completed_partition_retries_json_path", "completed_partition_retries"),
        ("completed_partition_retries_csv_path", "completed_partition_retries_csv"),
        (
            "stage3_completed_extraction_failure_summary_path",
            "stage3_completed_extraction_failure_summary",
        ),
        (
            "stage3_completed_extraction_exception_chain_path",
            "stage3_completed_extraction_exception_chain",
        ),
        (
            "stage3_completed_extraction_guardrail_path",
            "stage3_completed_extraction_guardrail",
        ),
    )
    pairs: list[tuple[str, str]] = []
    for attribute_name, label in labeled_attrs:
        path = _extract_error_attr(error, attribute_name)
        if path is not None:
            pairs.append((label, path))
    return tuple(pairs)


def _collect_failure_artifact_paths(error: BaseException) -> tuple[str, ...]:
    return tuple(path for _, path in _iter_failure_artifact_labels(error))