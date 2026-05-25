from __future__ import annotations

"""Deterministic contract validation for the first shared control-plane modules.

Canon ownership:
- Implements the buildable contract-validation seam required by the control-plane
  skeleton in the implementation mapping and backlog.
- Enforces machine-checkable contract boundaries without taking over feature
  semantics, raw-ingestion lineage, or episode orchestration meaning that belong
  to adjacent modules.
"""

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import UUID


class SchemaNotFoundError(FileNotFoundError):
    """Raised when a requested contract schema is not registered."""


class SchemaDefinitionError(ValueError):
    """Raised when a schema definition is malformed or unsupported."""


class ContractSchemaValidationError(ValueError):
    """Raised when a payload fails schema validation."""

    def __init__(self, contract_name: str, issues: Sequence["ValidationIssue"]) -> None:
        self.contract_name = contract_name
        self.issues = tuple(issues)
        message = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(f"Contract '{contract_name}' failed validation: {message}")


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    contract_name: str
    is_valid: bool
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class ContractSchema:
    contract_name: str
    schema_path: Path
    definition: Mapping[str, Any]


class SchemaRepository(Protocol):
    def load_schema(self, contract_name: str) -> ContractSchema:
        """Load the named contract schema."""


class AuditSink(Protocol):
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
    ) -> Any:
        """Record a structured audit event."""


class JsonContractSchemaRepository:
    """Loads schema definitions through a registry rather than code constants."""

    def __init__(self, repo_root: Path, registry_path: Path) -> None:
        self._repo_root = repo_root
        self._registry_path = registry_path
        self._registry_cache: dict[str, Any] | None = None

    def load_schema(self, contract_name: str) -> ContractSchema:
        registry = self._load_registry()
        contract_entry = registry["contracts"].get(contract_name)
        if contract_entry is None:
            raise SchemaNotFoundError(f"No schema registered for contract '{contract_name}'.")

        schema_path = self._repo_root / contract_entry["schema_path"]
        if not schema_path.exists():
            raise SchemaNotFoundError(
                f"Schema path for contract '{contract_name}' does not exist: {schema_path}"
            )

        definition = json.loads(schema_path.read_text(encoding="utf-8"))
        if definition.get("type") != "object":
            raise SchemaDefinitionError(
                f"Contract '{contract_name}' must have an object root type."
            )

        return ContractSchema(
            contract_name=contract_name,
            schema_path=schema_path,
            definition=definition,
        )

    def _load_registry(self) -> dict[str, Any]:
        if self._registry_cache is None:
            self._registry_cache = json.loads(self._registry_path.read_text(encoding="utf-8"))
        return self._registry_cache


class ContractSchemaValidator:
    """Validates contract payloads against a deterministic schema subset.

    Supported schema keys are intentionally narrow: ``type``, ``required``,
    ``properties``, ``additional_properties``, ``items``, ``enum``,
    ``min_length``, ``min_items``, and ``format``.
    """

    _TYPE_MAP: Mapping[str, tuple[type[Any], ...]] = {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "object": (dict,),
        "array": (list, tuple),
    }

    def __init__(self, schema_repository: SchemaRepository, audit_sink: AuditSink | None = None) -> None:
        self._schema_repository = schema_repository
        self._audit_sink = audit_sink

    def set_audit_sink(self, audit_sink: AuditSink) -> None:
        """Attach the audit sink after the audit store is available."""

        self._audit_sink = audit_sink

    def validate(
        self,
        contract_name: str,
        payload: Any,
        *,
        correlation_id: str,
        entity_type: str,
        entity_id: str,
        actor_id: str = "system",
        emit_audit_events: bool = True,
    ) -> ValidationResult:
        schema = self._schema_repository.load_schema(contract_name)
        normalized_payload = self._normalize(payload)
        issues: list[ValidationIssue] = []
        self._validate_node(schema.definition, normalized_payload, "$", issues)

        result = ValidationResult(
            contract_name=contract_name,
            is_valid=not issues,
            issues=tuple(issues),
        )

        if emit_audit_events and contract_name != "audit_event" and self._audit_sink is not None:
            event_type = (
                "platform.validation.contract_validated"
                if result.is_valid
                else "platform.validation.contract_validation_failed"
            )
            self._audit_sink.record_event(
                event_type=event_type,
                owner="platform.validation.contract_schema_validator",
                correlation_id=correlation_id,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor_id,
                payload={
                    "contract_name": contract_name,
                    "issues": [asdict(issue) for issue in result.issues],
                    "schema_path": str(schema.schema_path.relative_to(schema.schema_path.parents[2])),
                },
                tags=("contract-validation", contract_name),
            )

        return result

    def validate_or_raise(
        self,
        contract_name: str,
        payload: Any,
        *,
        correlation_id: str,
        entity_type: str,
        entity_id: str,
        actor_id: str = "system",
        emit_audit_events: bool = True,
    ) -> None:
        result = self.validate(
            contract_name,
            payload,
            correlation_id=correlation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            emit_audit_events=emit_audit_events,
        )
        if not result.is_valid:
            raise ContractSchemaValidationError(contract_name, result.issues)

    def _validate_node(
        self,
        schema: Mapping[str, Any],
        value: Any,
        path: str,
        issues: list[ValidationIssue],
    ) -> None:
        expected_type = schema.get("type")
        if expected_type:
            python_types = self._TYPE_MAP.get(expected_type)
            if python_types is None:
                raise SchemaDefinitionError(f"Unsupported schema type '{expected_type}' at {path}")
            if expected_type == "number" and isinstance(value, bool):
                issues.append(ValidationIssue(path, "Expected number but received boolean."))
                return
            if not isinstance(value, python_types):
                issues.append(
                    ValidationIssue(path, f"Expected {expected_type} but received {type(value).__name__}.")
                )
                return

        if "enum" in schema and value not in schema["enum"]:
            issues.append(ValidationIssue(path, f"Value '{value}' is not in the allowed enum."))

        if expected_type == "string":
            self._validate_string(schema, value, path, issues)
        elif expected_type == "array":
            self._validate_array(schema, value, path, issues)
        elif expected_type == "object":
            self._validate_object(schema, value, path, issues)

    def _validate_string(
        self,
        schema: Mapping[str, Any],
        value: str,
        path: str,
        issues: list[ValidationIssue],
    ) -> None:
        minimum = schema.get("min_length")
        if minimum is not None and len(value) < int(minimum):
            issues.append(ValidationIssue(path, f"String is shorter than min_length={minimum}."))

        value_format = schema.get("format")
        if value_format == "iso-datetime":
            try:
                datetime.fromisoformat(value)
            except ValueError as error:
                issues.append(ValidationIssue(path, f"Invalid ISO datetime: {error}"))
        elif value_format == "uuid":
            try:
                UUID(value)
            except ValueError as error:
                issues.append(ValidationIssue(path, f"Invalid UUID: {error}"))

    def _validate_array(
        self,
        schema: Mapping[str, Any],
        value: Sequence[Any],
        path: str,
        issues: list[ValidationIssue],
    ) -> None:
        minimum = schema.get("min_items")
        if minimum is not None and len(value) < int(minimum):
            issues.append(ValidationIssue(path, f"Array contains fewer than {minimum} items."))

        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                self._validate_node(item_schema, item, f"{path}[{index}]", issues)

    def _validate_object(
        self,
        schema: Mapping[str, Any],
        value: Mapping[str, Any],
        path: str,
        issues: list[ValidationIssue],
    ) -> None:
        required_keys = schema.get("required", [])
        properties = schema.get("properties", {})
        additional_properties = schema.get("additional_properties", True)

        for key in required_keys:
            if key not in value:
                issues.append(ValidationIssue(f"{path}.{key}", "Missing required property."))

        for key, item in value.items():
            if key in properties:
                self._validate_node(properties[key], item, f"{path}.{key}", issues)
            elif not additional_properties:
                issues.append(ValidationIssue(f"{path}.{key}", "Unexpected property."))

    def _normalize(self, payload: Any) -> Any:
        if is_dataclass(payload):
            return self._normalize(asdict(payload))
        if isinstance(payload, datetime):
            return payload.isoformat()
        if isinstance(payload, Path):
            return str(payload)
        if isinstance(payload, UUID):
            return str(payload)
        if isinstance(payload, dict):
            return {str(key): self._normalize(value) for key, value in payload.items()}
        if isinstance(payload, (list, tuple)):
            return [self._normalize(item) for item in payload]
        return payload
