from __future__ import annotations

"""Chunked persistence helpers for resumable promotions extraction partitions."""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
from typing import Literal

import pandas as pd

from data.promotions.promotion_base_extractor import PromotionExtractionManifest
from runtime.promotions.config import PromotionArtifactPaths


PromotionPartitionCompletionState = Literal[
    "in_progress",
    "compacting",
    "failed_incomplete",
    "finalized",
]
PromotionPartitionResumeState = Literal[
    "new_partition",
    "resume_incomplete_partition",
    "restart_completed_partition",
    "skip_finalized_partition",
]


class PromotionInvalidResumeStateError(RuntimeError):
    """Raised when persisted chunk or completion artifacts cannot be trusted for resume."""


class PromotionPartitionWriteError(RuntimeError):
    """Raised when a chunk cannot be persisted safely during extraction."""


class PromotionPartitionCompactionError(RuntimeError):
    """Raised when staged chunk files cannot be compacted into the final parquet."""


@dataclass(frozen=True)
class PromotionChunkedExtractionResumeDecision:
    resume_state: PromotionPartitionResumeState
    skipped_due_to_existing_completion: bool


@dataclass(frozen=True)
class PersistedChunkedPromotionExtraction:
    base_path: Path
    manifest_path: Path
    progress_path: Path
    completion_marker_path: Path
    fetch_mode: str
    chunk_count: int
    completed_chunk_count: int
    cumulative_rows_written: int
    partition_completion_state: PromotionPartitionCompletionState
    resume_state: PromotionPartitionResumeState
    skipped_due_to_existing_completion: bool = False


class PromotionChunkedExtractionWriter:
    """Persist bounded extraction chunks and finalize one trustworthy partition artifact."""

    def __init__(
        self,
        *,
        artifact_paths: PromotionArtifactPaths,
        run_id: str,
        stage_temp_chunk_files: bool,
    ) -> None:
        self._artifact_paths = artifact_paths
        self._run_id = run_id
        self._stage_temp_chunk_files = stage_temp_chunk_files
        self._base_path = artifact_paths.extracted_base_path(run_id)
        self._manifest_path = artifact_paths.extracted_manifest_path(run_id)
        self._progress_path = artifact_paths.extraction_partition_progress_path(run_id)
        self._completion_marker_path = artifact_paths.extraction_partition_completion_path(run_id)
        self._chunk_root = artifact_paths.extracted_chunk_root(run_id)
        self._temp_compaction_path = artifact_paths.extracted_compaction_temp_path(run_id)
        self._chunk_paths: list[Path] = []
        self._chunk_count = 0
        self._completed_chunk_count = 0
        self._cumulative_rows_written = 0
        self._resume_state: PromotionPartitionResumeState = "new_partition"
        self._fetch_mode = "chunked_fetch"
        self._chunk_row_count: int | None = None
        self._expected_columns: tuple[str, ...] | None = None
        self._parquet_writer = None

    @property
    def progress_path(self) -> Path:
        return self._progress_path

    @property
    def completion_marker_path(self) -> Path:
        return self._completion_marker_path

    def resolve_resume_decision(
        self,
        *,
        resume_completed_partitions: bool,
    ) -> PromotionChunkedExtractionResumeDecision:
        completion_payload = _read_optional_json(self._completion_marker_path)
        if completion_payload is not None:
            self._validate_completion_payload(completion_payload)
            if resume_completed_partitions:
                self._resume_state = "skip_finalized_partition"
                return PromotionChunkedExtractionResumeDecision(
                    resume_state="skip_finalized_partition",
                    skipped_due_to_existing_completion=True,
                )
            self._cleanup_existing_outputs()
            self._resume_state = "restart_completed_partition"
            return PromotionChunkedExtractionResumeDecision(
                resume_state="restart_completed_partition",
                skipped_due_to_existing_completion=False,
            )

        progress_payload = _read_optional_json(self._progress_path)
        if progress_payload is not None:
            if progress_payload.get("partition_completion_state") == "finalized":
                raise PromotionInvalidResumeStateError(
                    "Progress state claims finalized extraction without a completion marker."
                )
            self._cleanup_existing_outputs()
            self._resume_state = "resume_incomplete_partition"
            return PromotionChunkedExtractionResumeDecision(
                resume_state="resume_incomplete_partition",
                skipped_due_to_existing_completion=False,
            )

        self._resume_state = "new_partition"
        return PromotionChunkedExtractionResumeDecision(
            resume_state="new_partition",
            skipped_due_to_existing_completion=False,
        )

    def start_partition(
        self,
        *,
        fetch_mode: str,
        chunk_row_count: int,
    ) -> None:
        self._fetch_mode = fetch_mode
        self._chunk_row_count = chunk_row_count
        self._chunk_count = 0
        self._completed_chunk_count = 0
        self._cumulative_rows_written = 0
        self._chunk_paths = []
        self._expected_columns = None
        self._close_writer()
        self._write_progress(
            partition_completion_state="in_progress",
            skipped_due_to_existing_completion=False,
        )

    def write_chunk(self, frame: pd.DataFrame, *, chunk_index: int) -> Path | None:
        self._validate_chunk_frame(frame)
        try:
            if self._stage_temp_chunk_files:
                chunk_path = self._artifact_paths.extracted_chunk_path(self._run_id, chunk_index)
                chunk_path.parent.mkdir(parents=True, exist_ok=True)
                frame.to_parquet(chunk_path, index=False)
                self._chunk_paths.append(chunk_path)
                persisted_path: Path | None = chunk_path
            else:
                self._append_to_temp_parquet(frame)
                persisted_path = self._temp_compaction_path
            self._chunk_count = chunk_index
            self._completed_chunk_count = chunk_index
            self._cumulative_rows_written += len(frame.index)
            self._write_progress(
                partition_completion_state="in_progress",
                skipped_due_to_existing_completion=False,
                latest_chunk_path=(str(persisted_path) if persisted_path is not None else None),
            )
            return persisted_path
        except Exception as error:
            raise PromotionPartitionWriteError(
                f"Failed to persist chunk {chunk_index} for promotions extraction partition: {error}"
            ) from error

    def mark_failure(self, *, failure_message: str) -> None:
        self._close_writer()
        self._write_progress(
            partition_completion_state="failed_incomplete",
            skipped_due_to_existing_completion=False,
            failure_message=failure_message,
        )

    def discard_existing_outputs(self) -> None:
        self._cleanup_existing_outputs()

    def finalize(
        self,
        *,
        manifest: PromotionExtractionManifest,
    ) -> PersistedChunkedPromotionExtraction:
        try:
            self._write_progress(
                partition_completion_state="compacting",
                skipped_due_to_existing_completion=False,
            )
            self._base_path.parent.mkdir(parents=True, exist_ok=True)
            self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
            if self._completed_chunk_count == 0:
                pd.DataFrame(columns=list(manifest.columns)).to_parquet(self._base_path, index=False)
            elif self._stage_temp_chunk_files:
                self._compact_chunk_files()
            else:
                self._close_writer()
                if not self._temp_compaction_path.exists():
                    raise PromotionPartitionCompactionError(
                        "Temporary consolidated parquet was not created before finalization."
                    )
                self._temp_compaction_path.replace(self._base_path)
            self._manifest_path.write_text(
                json.dumps(manifest.to_dict(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            completion_payload = {
                "run_id": self._run_id,
                "fetch_mode": self._fetch_mode,
                "chunk_mode": manifest.chunk_mode,
                "chunk_row_count": self._chunk_row_count,
                "chunk_count": self._chunk_count,
                "completed_chunk_count": self._completed_chunk_count,
                "cumulative_rows_written": self._cumulative_rows_written,
                "batch_count": manifest.batch_count,
                "finalized_batch_count": manifest.finalized_batch_count,
                "resumed_batch_count": manifest.resumed_batch_count,
                "rebuilt_batch_count": manifest.rebuilt_batch_count,
                "total_landed_rows": manifest.total_landed_rows,
                "completion_state": manifest.completion_state or "finalized",
                "partition_completion_state": "finalized",
                "resume_state": self._resume_state,
                "skipped_due_to_existing_completion": False,
                "row_count": manifest.row_count,
                "promotion_row_key_checksum_sha256": (
                    manifest.promotion_row_key_checksum_sha256
                ),
                "base_path": str(self._base_path),
                "manifest_path": str(self._manifest_path),
                "completed_at_utc": _utc_now_iso(),
            }
            self._completion_marker_path.parent.mkdir(parents=True, exist_ok=True)
            self._completion_marker_path.write_text(
                json.dumps(completion_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self._write_progress(
                partition_completion_state="finalized",
                skipped_due_to_existing_completion=False,
            )
            if self._stage_temp_chunk_files and self._chunk_root.exists():
                shutil.rmtree(self._chunk_root)
            return PersistedChunkedPromotionExtraction(
                base_path=self._base_path,
                manifest_path=self._manifest_path,
                progress_path=self._progress_path,
                completion_marker_path=self._completion_marker_path,
                fetch_mode=self._fetch_mode,
                chunk_count=self._chunk_count,
                completed_chunk_count=self._completed_chunk_count,
                cumulative_rows_written=self._cumulative_rows_written,
                partition_completion_state="finalized",
                resume_state=self._resume_state,
            )
        except Exception as error:
            self.mark_failure(failure_message=str(error))
            if isinstance(error, PromotionPartitionCompactionError):
                raise
            raise PromotionPartitionCompactionError(
                f"Failed to finalize chunked promotions extraction partition: {error}"
            ) from error

    def _validate_completion_payload(self, payload: dict[str, object]) -> None:
        if payload.get("partition_completion_state") != "finalized":
            raise PromotionInvalidResumeStateError(
                "Completion marker does not declare a finalized partition state."
            )
        if not self._base_path.exists() or not self._manifest_path.exists():
            raise PromotionInvalidResumeStateError(
                "Completion marker exists but the finalized parquet or manifest is missing."
            )

    def _cleanup_existing_outputs(self) -> None:
        self._close_writer()
        if self._chunk_root.exists():
            shutil.rmtree(self._chunk_root)
        for path in (
            self._temp_compaction_path,
            self._base_path,
            self._manifest_path,
            self._completion_marker_path,
        ):
            if path.exists():
                path.unlink()

    def _validate_chunk_frame(self, frame: pd.DataFrame) -> None:
        columns = tuple(str(column_name) for column_name in frame.columns)
        if self._expected_columns is None:
            self._expected_columns = columns
            return
        if columns != self._expected_columns:
            raise PromotionPartitionWriteError(
                "Chunked promotions extraction changed columns mid-partition."
            )

    def _append_to_temp_parquet(self, frame: pd.DataFrame) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.Table.from_pandas(frame, preserve_index=False)
        self._temp_compaction_path.parent.mkdir(parents=True, exist_ok=True)
        if self._parquet_writer is None:
            self._parquet_writer = pq.ParquetWriter(
                str(self._temp_compaction_path),
                table.schema,
            )
        self._parquet_writer.write_table(table)

    def _compact_chunk_files(self) -> None:
        import pyarrow.parquet as pq

        if not self._chunk_paths:
            raise PromotionPartitionCompactionError(
                "No chunk parquet files were available for compaction."
            )
        writer = None
        try:
            self._temp_compaction_path.parent.mkdir(parents=True, exist_ok=True)
            for chunk_path in self._chunk_paths:
                table = pq.read_table(chunk_path)
                if writer is None:
                    writer = pq.ParquetWriter(str(self._temp_compaction_path), table.schema)
                writer.write_table(table)
            if writer is None:
                raise PromotionPartitionCompactionError(
                    "Chunk compaction did not receive any chunk tables to write."
                )
        finally:
            if writer is not None:
                writer.close()
        self._temp_compaction_path.replace(self._base_path)

    def _write_progress(
        self,
        *,
        partition_completion_state: PromotionPartitionCompletionState,
        skipped_due_to_existing_completion: bool,
        latest_chunk_path: str | None = None,
        failure_message: str | None = None,
    ) -> None:
        payload = {
            "run_id": self._run_id,
            "fetch_mode": self._fetch_mode,
            "chunk_row_count": self._chunk_row_count,
            "chunk_count": self._chunk_count,
            "completed_chunk_count": self._completed_chunk_count,
            "cumulative_rows_written": self._cumulative_rows_written,
            "completion_state": partition_completion_state,
            "partition_completion_state": partition_completion_state,
            "resume_state": self._resume_state,
            "skipped_due_to_existing_completion": skipped_due_to_existing_completion,
            "stage_temp_chunk_files": self._stage_temp_chunk_files,
            "chunk_root": str(self._chunk_root),
            "temp_compaction_path": str(self._temp_compaction_path),
            "base_path": str(self._base_path),
            "manifest_path": str(self._manifest_path),
            "completion_marker_path": str(self._completion_marker_path),
            "latest_chunk_path": latest_chunk_path,
            "failure_message": failure_message,
            "updated_at_utc": _utc_now_iso(),
        }
        self._progress_path.parent.mkdir(parents=True, exist_ok=True)
        self._progress_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _close_writer(self) -> None:
        if self._parquet_writer is not None:
            self._parquet_writer.close()
            self._parquet_writer = None


def _read_optional_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()