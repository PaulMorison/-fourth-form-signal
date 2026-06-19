from __future__ import annotations

"""Governed feature registration for the first shared control-plane batch.

Canon ownership:
- Implements feature identity, semantic scope, owner namespace checks, and
  contract validation for the first reusable feature definitions.
- Does not implement dataset versioning, feature generation, or model use;
  those remain adjacent canon-owned modules.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator


class FeatureRegistryError(ValueError):
    """Base error for feature-governance failures."""


class FeatureOwnerNotRegisteredError(FeatureRegistryError):
    """Raised when a feature owner is not registered in the ownership registry."""


class DuplicateFeatureDefinitionError(FeatureRegistryError):
    """Raised when a feature name is registered twice."""


class FeatureSemanticValidationError(FeatureRegistryError):
    """Raised when a feature definition violates semantic rules."""


@dataclass(frozen=True)
class FeatureOwnerDefinition:
    owner_id: str
    allowed_namespaces: tuple[str, ...]
    semantic_scope: str


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    namespace: str
    owner_id: str
    description: str
    semantic_scope: str
    formula: str
    unit: str
    denominator: str | None
    time_basis: str
    window: str
    data_type: str
    status: str
    source_fields: tuple[str, ...]
    created_at: datetime

    def to_contract_dict(self) -> dict[str, Any]:
        contract = {
            "name": self.name,
            "namespace": self.namespace,
            "owner_id": self.owner_id,
            "description": self.description,
            "semantic_scope": self.semantic_scope,
            "formula": self.formula,
            "unit": self.unit,
            "time_basis": self.time_basis,
            "window": self.window,
            "data_type": self.data_type,
            "status": self.status,
            "source_fields": list(self.source_fields),
            "created_at": self.created_at.isoformat(),
        }
        if self.denominator is not None:
            contract["denominator"] = self.denominator
        return contract


class FeatureDefinitionRepository(Protocol):
    def save(self, definition: FeatureDefinition) -> None:
        """Persist a feature definition."""

    def get(self, feature_name: str) -> FeatureDefinition | None:
        """Return the named feature definition when it exists."""

    def list_definitions(self) -> Sequence[FeatureDefinition]:
        """Return all feature definitions."""


class FeatureOwnerRegistry(Protocol):
    def get_owner(self, owner_id: str) -> FeatureOwnerDefinition:
        """Return the owning namespace definition for a feature owner."""


class InMemoryFeatureDefinitionRepository:
    """A deterministic repository seam for governed feature definitions."""

    def __init__(self) -> None:
        self._definitions: dict[str, FeatureDefinition] = {}

    def save(self, definition: FeatureDefinition) -> None:
        self._definitions[definition.name] = definition

    def get(self, feature_name: str) -> FeatureDefinition | None:
        return self._definitions.get(feature_name)

    def list_definitions(self) -> Sequence[FeatureDefinition]:
        return tuple(self._definitions.values())


class JsonFeatureOwnerRegistry:
    """Loads feature owners and allowed namespaces from a checked-in registry."""

    def __init__(self, registry_path: Path) -> None:
        content = json.loads(registry_path.read_text(encoding="utf-8"))
        self._owners = {
            owner_id: FeatureOwnerDefinition(
                owner_id=owner_id,
                allowed_namespaces=tuple(owner["allowed_namespaces"]),
                semantic_scope=owner["semantic_scope"],
            )
            for owner_id, owner in content["owners"].items()
        }

    def get_owner(self, owner_id: str) -> FeatureOwnerDefinition:
        try:
            return self._owners[owner_id]
        except KeyError as error:
            raise FeatureOwnerNotRegisteredError(
                f"Feature owner '{owner_id}' is not registered."
            ) from error


class FeatureRegistry:
    """Registers governed features with explicit owner and semantic checks."""

    def __init__(
        self,
        *,
        owner_registry: FeatureOwnerRegistry,
        repository: FeatureDefinitionRepository,
        contract_validator: ContractSchemaValidator,
        audit_event_store: AuditEventStore,
    ) -> None:
        self._owner_registry = owner_registry
        self._repository = repository
        self._contract_validator = contract_validator
        self._audit_event_store = audit_event_store

    def register_feature(
        self,
        definition: FeatureDefinition,
        *,
        correlation_id: str,
        actor_id: str,
    ) -> FeatureDefinition:
        if self._repository.get(definition.name) is not None:
            raise DuplicateFeatureDefinitionError(
                f"Feature '{definition.name}' is already registered."
            )

        owner = self._owner_registry.get_owner(definition.owner_id)
        self._validate_feature(definition, owner)
        self._contract_validator.validate_or_raise(
            "feature_definition",
            definition.to_contract_dict(),
            correlation_id=correlation_id,
            entity_type="feature_definition",
            entity_id=definition.name,
            actor_id=actor_id,
        )
        self._repository.save(definition)
        self._audit_event_store.record_event(
            event_type="state.features.feature_registered",
            owner="state.features.feature_registry",
            correlation_id=correlation_id,
            entity_type="feature_definition",
            entity_id=definition.name,
            actor_id=actor_id,
            payload={
                "owner_id": definition.owner_id,
                "namespace": definition.namespace,
                "time_basis": definition.time_basis,
                "window": definition.window,
            },
            tags=("feature-registry", definition.namespace),
        )
        return definition

    def get_feature(self, feature_name: str) -> FeatureDefinition | None:
        return self._repository.get(feature_name)

    def feature_exists(self, feature_name: str) -> bool:
        return self.get_feature(feature_name) is not None

    def list_features(self) -> Sequence[FeatureDefinition]:
        return self._repository.list_definitions()

    def _validate_feature(
        self,
        definition: FeatureDefinition,
        owner: FeatureOwnerDefinition,
    ) -> None:
        if not definition.name.startswith(f"{definition.namespace}."):
            raise FeatureSemanticValidationError(
                "Feature names must start with their namespace followed by a dot."
            )
        if definition.namespace not in owner.allowed_namespaces:
            raise FeatureSemanticValidationError(
                f"Owner '{owner.owner_id}' cannot register namespace '{definition.namespace}'."
            )
        if definition.semantic_scope != owner.semantic_scope:
            raise FeatureSemanticValidationError(
                "Feature semantic scope must match the registered owner semantic scope."
            )
        if not definition.formula.strip():
            raise FeatureSemanticValidationError("Feature formula must be non-empty.")
        if definition.unit == "ratio" and not definition.denominator:
            raise FeatureSemanticValidationError(
                "Ratio features must declare a denominator explicitly."
            )
        if not definition.source_fields:
            raise FeatureSemanticValidationError(
                "Feature definitions must declare at least one source field."
            )
