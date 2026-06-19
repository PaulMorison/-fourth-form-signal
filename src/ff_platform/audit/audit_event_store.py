from __future__ import annotations

"""Governed audit-event persistence for the first shared control-plane batch.

Canon ownership:
- Implements explicit audit outputs for governed transitions in validation,
  ingestion, feature registration, and decision-case orchestration.
- Preserves structured event lineage without taking over runtime telemetry,
  release monitoring, or feature semantics that belong to adjacent modules.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator


class AuditEventStoreError(ValueError):
    """Base error for audit-event storage failures."""


class AuditEventTypeNotRegisteredError(AuditEventStoreError):
    """Raised when an event type is emitted outside the registered ownership map."""


class AuditPersistenceError(AuditEventStoreError):
    """Raised when an audit event cannot be persisted."""


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: str
    owner: str
    correlation_id: str
    entity_type: str
    entity_id: str
    actor_id: str
    occurred_at: datetime
    payload: Mapping[str, Any]
    tags: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "owner": self.owner,
            "correlation_id": self.correlation_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "actor_id": self.actor_id,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": dict(self.payload),
            "tags": list(self.tags),
        }


class AuditEventRepository(Protocol):
    def append(self, event: AuditEvent) -> None:
        """Persist a single audit event."""

    def list_events(self) -> Sequence[AuditEvent]:
        """Return all persisted audit events."""


class AuditEventTypeRegistry(Protocol):
    def require_owner(self, event_type: str) -> str:
        """Return the registered owner for an event type."""


class InMemoryAuditEventRepository:
    """A narrow, unit-testable audit event repository."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def list_events(self) -> Sequence[AuditEvent]:
        return tuple(self._events)


class JsonAuditEventTypeRegistry:
    """Loads event ownership from a registry file rather than code constants."""

    def __init__(self, registry_path: Path) -> None:
        self._registry_path = registry_path
        content = json.loads(self._registry_path.read_text(encoding="utf-8"))
        self._event_type_map: dict[str, str] = {
            entry["name"]: entry["owner"] for entry in content["event_types"]
        }

    def require_owner(self, event_type: str) -> str:
        try:
            return self._event_type_map[event_type]
        except KeyError as error:
            raise AuditEventTypeNotRegisteredError(
                f"Audit event type '{event_type}' is not registered."
            ) from error


class AuditEventStore:
    """Validates and persists governed audit events.

    The store validates event-type ownership against a registry and validates the
    persisted event shape against the `audit_event` contract schema. It does not
    emit recursive self-audit events; the stored event itself is the audit output.
    """

    def __init__(
        self,
        *,
        event_type_registry: AuditEventTypeRegistry,
        repository: AuditEventRepository,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._event_type_registry = event_type_registry
        self._repository = repository
        self._contract_validator = contract_validator

    def record_event(
        self,
        *,
        event_type: str,
        owner: str,
        correlation_id: str,
        entity_type: str,
        entity_id: str,
        payload: Mapping[str, Any],
        actor_id: str = "system",
        tags: Sequence[str] = (),
    ) -> AuditEvent:
        registered_owner = self._event_type_registry.require_owner(event_type)
        if registered_owner != owner:
            raise AuditEventTypeNotRegisteredError(
                f"Event type '{event_type}' is owned by '{registered_owner}', not '{owner}'."
            )

        event = AuditEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            owner=owner,
            correlation_id=correlation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            occurred_at=datetime.now(tz=UTC),
            payload=dict(payload),
            tags=tuple(tags),
        )
        self._contract_validator.validate_or_raise(
            "audit_event",
            event.to_contract_dict(),
            correlation_id=correlation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            emit_audit_events=False,
        )

        try:
            self._repository.append(event)
        except Exception as error:  # pragma: no cover - seam for repo failures
            raise AuditPersistenceError(f"Failed to persist audit event: {error}") from error

        return event

    def list_events(self) -> Sequence[AuditEvent]:
        return self._repository.list_events()
