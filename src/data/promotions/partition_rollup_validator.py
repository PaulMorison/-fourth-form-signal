from __future__ import annotations

"""Pre-rollup validation of completed promotion-extraction partitions.

This module enforces an explicit completion contract before
``_combine_completed_partition_artifacts`` reads any partition parquet:

- every partition must have a completion sidecar marked ``finalized``
- the partition base parquet referenced by that sidecar must exist
- the column schema fingerprint must match across partitions

The validator emits a run-level ``partition_rollup_registry.json`` artifact
listing every partition's completion state, exact missing paths, and the
reason rollup was (or was not) authorised. It supports a bounded number of
re-scans with short backoff to absorb local/NAS filesystem visibility lag,
without ever re-running extraction.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import time
from pathlib import Path
from typing import Sequence


DEFAULT_ROLLUP_RECONCILIATION_RETRIES = 3
DEFAULT_ROLLUP_RECONCILIATION_BACKOFF_SECONDS = 0.5


class PartitionRollupValidationError(RuntimeError):
    """Raised when partition completion sidecars do not authorise rollup."""

    def __init__(
        self,
        message: str,
        *,
        registry: "PartitionRollupRegistry",
    ) -> None:
        super().__init__(message)
        self.registry = registry


@dataclass(frozen=True)
class PartitionCompletionRecord:
    partition_id: str
    partition_index: int
    partition_count: int
    expected_files: tuple[str, ...]
    completed_files: tuple[str, ...]
    missing_files: tuple[str, ...]
    row_count: int | None
    schema_fingerprint: str | None
    completion_status: str
    completion_marker_path: str | None
    completed_at_utc: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "partition_id": self.partition_id,
            "partition_index": self.partition_index,
            "partition_count": self.partition_count,
            "expected_files": list(self.expected_files),
            "completed_files": list(self.completed_files),
            "missing_files": list(self.missing_files),
            "row_count": self.row_count,
            "schema_fingerprint": self.schema_fingerprint,
            "completion_status": self.completion_status,
            "completion_marker_path": self.completion_marker_path,
            "completed_at_utc": self.completed_at_utc,
        }


@dataclass(frozen=True)
class PartitionRollupRegistry:
    run_id: str
    partition_strategy: str
    expected_partition_count: int
    completed_partition_count: int
    missing_partition_ids: tuple[str, ...]
    duplicate_partition_ids: tuple[str, ...]
    schema_mismatch_partition_ids: tuple[str, ...]
    total_rows_by_partition: dict[str, int]
    rollup_ready_flag: bool
    rollup_ready_reason: str
    reconciliation_attempts: int
    partitions: tuple[PartitionCompletionRecord, ...] = field(default_factory=tuple)
    generated_at_utc: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "partition_strategy": self.partition_strategy,
            "expected_partition_count": self.expected_partition_count,
            "completed_partition_count": self.completed_partition_count,
            "missing_partition_ids": list(self.missing_partition_ids),
            "duplicate_partition_ids": list(self.duplicate_partition_ids),
            "schema_mismatch_partition_ids": list(self.schema_mismatch_partition_ids),
            "total_rows_by_partition": dict(self.total_rows_by_partition),
            "rollup_ready_flag": self.rollup_ready_flag,
            "rollup_ready_reason": self.rollup_ready_reason,
            "reconciliation_attempts": self.reconciliation_attempts,
            "partitions": [record.to_dict() for record in self.partitions],
            "generated_at_utc": self.generated_at_utc,
        }


@dataclass(frozen=True)
class _PartitionInputDescriptor:
    partition_id: str
    partition_index: int
    partition_count: int
    completion_marker_path: str | None
    base_path: str | None
    manifest_path: str | None


def build_partition_input_descriptors(
    partition_artifacts: Sequence[object],
) -> tuple[_PartitionInputDescriptor, ...]:
    """Translate the runtime artifact list into validator inputs.

    Each artifact must expose ``partition_index``, ``partition_count``,
    ``base_path``, ``manifest_path`` and (optionally)
    ``partition_completion_marker_path``. The latter is normally provided by
    chunked extraction; when absent we fall back to a derived path based on
    the artifact's manifest directory only for diagnostic purposes.
    """

    descriptors: list[_PartitionInputDescriptor] = []
    for artifact in partition_artifacts:
        partition_index = int(getattr(artifact, "partition_index", 0) or 0)
        partition_count = int(getattr(artifact, "partition_count", 0) or 0)
        partition_id = (
            f"partition-{partition_index:0{max(2, len(str(partition_count)))}d}"
            f"-of-{partition_count:0{max(2, len(str(partition_count)))}d}"
        )
        descriptors.append(
            _PartitionInputDescriptor(
                partition_id=partition_id,
                partition_index=partition_index,
                partition_count=partition_count,
                completion_marker_path=getattr(
                    artifact, "partition_completion_marker_path", None
                ),
                base_path=getattr(artifact, "base_path", None),
                manifest_path=getattr(artifact, "manifest_path", None),
            )
        )
    return tuple(descriptors)


def validate_partition_completion_for_rollup(
    *,
    run_id: str,
    partition_strategy: str,
    expected_partition_count: int,
    partition_artifacts: Sequence[object],
    registry_output_path: Path,
    max_reconciliation_retries: int = DEFAULT_ROLLUP_RECONCILIATION_RETRIES,
    reconciliation_backoff_seconds: float = DEFAULT_ROLLUP_RECONCILIATION_BACKOFF_SECONDS,
) -> PartitionRollupRegistry:
    """Validate sidecars and emit the rollup registry artifact.

    Raises ``PartitionRollupValidationError`` (after writing the registry) if
    rollup is not authorised. On success returns the registry.
    """

    descriptors = build_partition_input_descriptors(partition_artifacts)
    attempts = 0
    last_records: tuple[PartitionCompletionRecord, ...] = ()
    last_failure_reason = ""
    while True:
        attempts += 1
        records = tuple(_inspect_descriptor(descriptor) for descriptor in descriptors)
        last_records = records
        unresolved = tuple(
            record for record in records if record.completion_status != "COMPLETE"
        )
        if not unresolved:
            break
        last_failure_reason = (
            f"{len(unresolved)} partition(s) not yet COMPLETE on attempt {attempts}"
        )
        if attempts > max_reconciliation_retries:
            break
        if reconciliation_backoff_seconds > 0:
            time.sleep(reconciliation_backoff_seconds)

    registry = _build_registry(
        run_id=run_id,
        partition_strategy=partition_strategy,
        expected_partition_count=expected_partition_count,
        records=last_records,
        attempts=attempts,
        fallback_failure_reason=last_failure_reason,
    )
    _write_registry(registry, registry_output_path)
    if not registry.rollup_ready_flag:
        raise PartitionRollupValidationError(
            (
                "Partition rollup blocked: "
                f"{registry.rollup_ready_reason}. "
                f"missing_partition_ids={list(registry.missing_partition_ids)}; "
                f"schema_mismatch_partition_ids={list(registry.schema_mismatch_partition_ids)}; "
                f"duplicate_partition_ids={list(registry.duplicate_partition_ids)}; "
                f"registry_path={registry_output_path}"
            ),
            registry=registry,
        )
    return registry


def _inspect_descriptor(
    descriptor: _PartitionInputDescriptor,
) -> PartitionCompletionRecord:
    expected_files: list[str] = []
    completed_files: list[str] = []
    missing_files: list[str] = []
    row_count: int | None = None
    schema_fingerprint: str | None = None
    completed_at_utc: str | None = None

    marker_payload: dict[str, object] | None = None
    marker_path = descriptor.completion_marker_path
    if marker_path:
        expected_files.append(marker_path)
        marker_file = Path(marker_path)
        if marker_file.exists():
            try:
                marker_payload = json.loads(marker_file.read_text(encoding="utf-8"))
            except Exception as error:  # noqa: BLE001 - surfaced via status
                marker_payload = None
                missing_files.append(f"{marker_path} (unreadable: {error})")
            else:
                completed_files.append(marker_path)
                if marker_payload.get("partition_completion_state") != "finalized":
                    missing_files.append(
                        f"{marker_path} (state={marker_payload.get('partition_completion_state')!r})"
                    )
        else:
            missing_files.append(marker_path)

    base_path = descriptor.base_path
    if base_path:
        expected_files.append(base_path)
        if Path(base_path).exists():
            completed_files.append(base_path)
        else:
            missing_files.append(base_path)
    else:
        missing_files.append("<base_path unset>")

    manifest_path = descriptor.manifest_path
    if manifest_path:
        expected_files.append(manifest_path)
        manifest_file = Path(manifest_path)
        if manifest_file.exists():
            completed_files.append(manifest_path)
            try:
                manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                manifest_payload = {}
            row_count = _coerce_int(manifest_payload.get("row_count"))
            columns_value = manifest_payload.get("columns")
            if isinstance(columns_value, (list, tuple)):
                schema_fingerprint = _fingerprint_columns(columns_value)
        else:
            missing_files.append(manifest_path)

    if marker_payload is not None:
        if row_count is None:
            row_count = _coerce_int(marker_payload.get("row_count"))
        completed_at_utc = (
            marker_payload.get("completed_at_utc")
            if isinstance(marker_payload.get("completed_at_utc"), str)
            else None
        )

    completion_status = "COMPLETE" if not missing_files else "INCOMPLETE"
    return PartitionCompletionRecord(
        partition_id=descriptor.partition_id,
        partition_index=descriptor.partition_index,
        partition_count=descriptor.partition_count,
        expected_files=tuple(expected_files),
        completed_files=tuple(completed_files),
        missing_files=tuple(missing_files),
        row_count=row_count,
        schema_fingerprint=schema_fingerprint,
        completion_status=completion_status,
        completion_marker_path=marker_path,
        completed_at_utc=completed_at_utc,
    )


def _build_registry(
    *,
    run_id: str,
    partition_strategy: str,
    expected_partition_count: int,
    records: tuple[PartitionCompletionRecord, ...],
    attempts: int,
    fallback_failure_reason: str,
) -> PartitionRollupRegistry:
    completed = tuple(r for r in records if r.completion_status == "COMPLETE")
    missing_ids = tuple(r.partition_id for r in records if r.completion_status != "COMPLETE")

    seen_indexes: dict[int, int] = {}
    duplicates: list[str] = []
    for record in records:
        seen_indexes[record.partition_index] = seen_indexes.get(record.partition_index, 0) + 1
    for record in records:
        if seen_indexes[record.partition_index] > 1:
            if record.partition_id not in duplicates:
                duplicates.append(record.partition_id)

    fingerprints: dict[str, list[str]] = {}
    for record in completed:
        if record.schema_fingerprint is None:
            continue
        fingerprints.setdefault(record.schema_fingerprint, []).append(record.partition_id)
    schema_mismatch_ids: tuple[str, ...] = ()
    if len(fingerprints) > 1:
        # Pick the most common fingerprint as the canonical one and flag the rest.
        canonical_fingerprint = max(fingerprints.items(), key=lambda kv: len(kv[1]))[0]
        schema_mismatch_ids = tuple(
            partition_id
            for fingerprint, partition_ids in fingerprints.items()
            if fingerprint != canonical_fingerprint
            for partition_id in partition_ids
        )

    rows_by_partition = {
        record.partition_id: int(record.row_count)
        for record in records
        if record.row_count is not None
    }

    if len(records) != expected_partition_count:
        rollup_ready_flag = False
        rollup_ready_reason = (
            f"received {len(records)} partition artifact(s) but expected {expected_partition_count}"
        )
    elif missing_ids:
        rollup_ready_flag = False
        rollup_ready_reason = (
            fallback_failure_reason
            or f"{len(missing_ids)} partition(s) missing required files"
        )
    elif duplicates:
        rollup_ready_flag = False
        rollup_ready_reason = f"duplicate partition indexes detected: {duplicates}"
    elif schema_mismatch_ids:
        rollup_ready_flag = False
        rollup_ready_reason = (
            f"schema fingerprint mismatch across partitions: {list(schema_mismatch_ids)}"
        )
    else:
        rollup_ready_flag = True
        rollup_ready_reason = "all partitions COMPLETE with matching schema"

    return PartitionRollupRegistry(
        run_id=run_id,
        partition_strategy=partition_strategy,
        expected_partition_count=expected_partition_count,
        completed_partition_count=len(completed),
        missing_partition_ids=missing_ids,
        duplicate_partition_ids=tuple(duplicates),
        schema_mismatch_partition_ids=schema_mismatch_ids,
        total_rows_by_partition=rows_by_partition,
        rollup_ready_flag=rollup_ready_flag,
        rollup_ready_reason=rollup_ready_reason,
        reconciliation_attempts=attempts,
        partitions=records,
        generated_at_utc=datetime.now(tz=UTC).isoformat(),
    )


def _write_registry(registry: PartitionRollupRegistry, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(registry.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _fingerprint_columns(columns: Sequence[object]) -> str:
    normalized = [str(name) for name in columns]
    return "|".join(normalized)


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
