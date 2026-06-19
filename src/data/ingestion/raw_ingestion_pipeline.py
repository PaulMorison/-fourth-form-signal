from __future__ import annotations

"""Governed raw-data intake for the first shared control-plane batch.

Canon ownership:
- Implements raw-source intake, source validation, required payload checks,
  lineage hashing, and audit emission for the initial shared pipeline slice.
- Does not implement staging, canonical entity mapping, or feature generation;
  those remain adjacent modules owned elsewhere in the canon.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator


class RawIngestionError(ValueError):
    """Base error for raw-ingestion failures."""


class UnknownIngestionSourceError(RawIngestionError):
    """Raised when a raw record references an unknown governed source."""


class DuplicateRawRecordError(RawIngestionError):
    """Raised when the same source record is ingested twice."""


class RawPayloadValidationError(RawIngestionError):
    """Raised when a payload does not satisfy source-specific rules."""


@dataclass(frozen=True)
class IngestionSourceDefinition:
    source_name: str
    entity_type: str
    allowed_scopes: tuple[str, ...]
    required_payload_fields: tuple[str, ...]


@dataclass(frozen=True)
class RawIngestionCommand:
    source_name: str
    source_record_id: str
    scope_key: str
    scope_type: str
    observed_at: datetime
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RawIngestionRecord:
    raw_record_id: str
    source_name: str
    source_record_id: str
    entity_type: str
    scope_key: str
    scope_type: str
    observed_at: datetime
    acquired_at: datetime
    lineage_hash: str
    payload: Mapping[str, Any]

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "raw_record_id": self.raw_record_id,
            "source_name": self.source_name,
            "source_record_id": self.source_record_id,
            "entity_type": self.entity_type,
            "scope_key": self.scope_key,
            "scope_type": self.scope_type,
            "observed_at": self.observed_at.isoformat(),
            "acquired_at": self.acquired_at.isoformat(),
            "lineage_hash": self.lineage_hash,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class RawIngestionBatchResult:
    accepted_records: tuple[RawIngestionRecord, ...]


class RawRecordRepository(Protocol):
    def exists(self, source_name: str, source_record_id: str) -> bool:
        """Return True when a source record has already been ingested."""

    def save(self, record: RawIngestionRecord) -> None:
        """Persist an accepted raw record."""

    def list_records(self) -> Sequence[RawIngestionRecord]:
        """Return all raw records."""


class IngestionSourceRegistry(Protocol):
    def get_source(self, source_name: str) -> IngestionSourceDefinition:
        """Load the governing definition for a raw source."""


class InMemoryRawRecordRepository:
    """Simple raw-record repository for deterministic bootstrapping and tests."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], RawIngestionRecord] = {}

    def exists(self, source_name: str, source_record_id: str) -> bool:
        return (source_name, source_record_id) in self._records

    def save(self, record: RawIngestionRecord) -> None:
        self._records[(record.source_name, record.source_record_id)] = record

    def list_records(self) -> Sequence[RawIngestionRecord]:
        return tuple(self._records.values())


class JsonIngestionSourceRegistry:
    """Registry-backed source definitions for raw-data ownership."""

    def __init__(self, registry_path: Path) -> None:
        content = json.loads(registry_path.read_text(encoding="utf-8"))
        self._sources = {
            name: IngestionSourceDefinition(
                source_name=name,
                entity_type=entry["entity_type"],
                allowed_scopes=tuple(entry["allowed_scopes"]),
                required_payload_fields=tuple(entry["required_payload_fields"]),
            )
            for name, entry in content["sources"].items()
        }

    def get_source(self, source_name: str) -> IngestionSourceDefinition:
        try:
            return self._sources[source_name]
        except KeyError as error:
            raise UnknownIngestionSourceError(
                f"Source '{source_name}' is not registered for raw ingestion."
            ) from error


class RawIngestionPipeline:
    """Validates and persists raw records before any downstream transformation.

    The module intentionally stops at raw-record legitimacy so it does not absorb
    staging, canonicalization, or feature-generation ownership.
    """

    def __init__(
        self,
        *,
        source_registry: IngestionSourceRegistry,
        repository: RawRecordRepository,
        contract_validator: ContractSchemaValidator,
        audit_event_store: AuditEventStore,
    ) -> None:
        self._source_registry = source_registry
        self._repository = repository
        self._contract_validator = contract_validator
        self._audit_event_store = audit_event_store

    def ingest_batch(
        self,
        commands: Sequence[RawIngestionCommand],
        *,
        correlation_id: str,
        actor_id: str,
    ) -> RawIngestionBatchResult:
        accepted_records: list[RawIngestionRecord] = []

        for command in commands:
            source = self._source_registry.get_source(command.source_name)
            if self._repository.exists(command.source_name, command.source_record_id):
                error = DuplicateRawRecordError(
                    f"Duplicate raw record '{command.source_name}:{command.source_record_id}'."
                )
                self._audit_event_store.record_event(
                    event_type="data.ingestion.raw_record_rejected",
                    owner="data.ingestion.raw_ingestion_pipeline",
                    correlation_id=correlation_id,
                    entity_type=source.entity_type,
                    entity_id=command.source_record_id,
                    actor_id=actor_id,
                    payload={"reason": str(error), "source_name": command.source_name},
                    tags=("raw-ingestion", "duplicate"),
                )
                raise error

            self._validate_source_payload(command, source)
            record = self._build_record(command, source)
            self._contract_validator.validate_or_raise(
                "raw_ingestion_record",
                record.to_contract_dict(),
                correlation_id=correlation_id,
                entity_type=record.entity_type,
                entity_id=record.raw_record_id,
                actor_id=actor_id,
            )
            self._repository.save(record)
            accepted_records.append(record)
            self._audit_event_store.record_event(
                event_type="data.ingestion.raw_record_ingested",
                owner="data.ingestion.raw_ingestion_pipeline",
                correlation_id=correlation_id,
                entity_type=record.entity_type,
                entity_id=record.raw_record_id,
                actor_id=actor_id,
                payload={
                    "source_name": record.source_name,
                    "source_record_id": record.source_record_id,
                    "scope_key": record.scope_key,
                    "lineage_hash": record.lineage_hash,
                },
                tags=("raw-ingestion", record.scope_type),
            )

        return RawIngestionBatchResult(accepted_records=tuple(accepted_records))

    def _validate_source_payload(
        self,
        command: RawIngestionCommand,
        source: IngestionSourceDefinition,
    ) -> None:
        if command.scope_type not in source.allowed_scopes:
            raise RawPayloadValidationError(
                f"Source '{source.source_name}' does not allow scope '{command.scope_type}'."
            )

        if not command.source_record_id.strip():
            raise RawPayloadValidationError("source_record_id must be non-empty.")

        missing_fields = [
            field_name
            for field_name in source.required_payload_fields
            if field_name not in command.payload
        ]
        if missing_fields:
            raise RawPayloadValidationError(
                f"Payload is missing required fields for source '{source.source_name}': {missing_fields}"
            )

    def _build_record(
        self,
        command: RawIngestionCommand,
        source: IngestionSourceDefinition,
    ) -> RawIngestionRecord:
        normalized_payload = json.dumps(command.payload, sort_keys=True, separators=(",", ":"))
        lineage_hash = hashlib.sha256(
            f"{command.source_name}:{command.source_record_id}:{normalized_payload}".encode("utf-8")
        ).hexdigest()
        return RawIngestionRecord(
            raw_record_id=str(uuid4()),
            source_name=command.source_name,
            source_record_id=command.source_record_id,
            entity_type=source.entity_type,
            scope_key=command.scope_key,
            scope_type=command.scope_type,
            observed_at=command.observed_at,
            acquired_at=datetime.now(tz=UTC),
            lineage_hash=lineage_hash,
            payload=dict(command.payload),
        )
