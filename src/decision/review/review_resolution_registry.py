from __future__ import annotations

"""Registry-backed review resolution classes and case disposition classes.

Canon ownership:
- Owns governed review-resolution class identity and governed case-disposition
  class identity for explicit post-packet review settlement.
- Does not execute recommendation generation, action-instruction issuance,
  escalation workflow, or reopen logic.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_RESOLUTION_STATES = {"settled", "returned", "deferred", "unresolved"}
_VALID_REVIEW_OUTCOMES = {
    "resolved_with_action",
    "resolved_with_non_action",
    "resolved_with_escalation",
    "returned_for_rework",
    "returned_for_clarification",
    "deferred_continuation",
    "unresolved_state",
    "rejected_resolution",
}
_VALID_PACKET_STATUSES = {"ready_for_handoff", "fallback_template_applied"}
_VALID_DISPOSITION_STATES = {
    "action_routing",
    "non_action_closure",
    "reroute",
    "rework",
    "clarification",
    "deferred_continuation",
    "governed_unresolved_closure",
}
_VALID_CLOSURE_STATES = {
    "open",
    "closed",
    "closed_pending_downstream_execution",
    "closed_pending_later_review",
    "closed_with_qualified_finality",
}
_VALID_CLOSURE_QUALITIES = {"complete", "qualified"}


class ReviewResolutionRegistryError(ValueError):
    """Base error for review-resolution registry failures."""


@dataclass(frozen=True)
class ReviewResolutionClassDefinition:
    resolution_class_id: str
    description: str
    resolution_state: str
    review_outcome: str
    disposition_class_id: str
    allowed_packet_statuses: tuple[str, ...]
    required_resolution_fields: tuple[str, ...]
    optional_resolution_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class CaseDispositionClassDefinition:
    disposition_class_id: str
    description: str
    disposition_state: str
    closure_state: str
    closure_quality: str
    terminality: bool
    status: str
    lineage: Mapping[str, str]
    reopen_reference: str | None = None


class ReviewResolutionRegistry(Protocol):
    def get_resolution_class(self, resolution_class_id: str) -> ReviewResolutionClassDefinition:
        """Return the named review-resolution class."""

    def get_disposition_class(
        self,
        disposition_class_id: str,
    ) -> CaseDispositionClassDefinition:
        """Return the named case-disposition class."""


class JsonReviewResolutionRegistry:
    """Loads review-resolution and disposition classes from checked-in registries."""

    def __init__(
        self,
        *,
        review_resolution_classes_path: Path,
        case_disposition_classes_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._disposition_classes = self._load_disposition_classes(case_disposition_classes_path)
        self._resolution_classes = self._load_resolution_classes(review_resolution_classes_path)
        self._validate_cross_registry_links()

    def get_resolution_class(self, resolution_class_id: str) -> ReviewResolutionClassDefinition:
        try:
            return self._resolution_classes[resolution_class_id]
        except KeyError as error:
            raise ReviewResolutionRegistryError(
                f"Review resolution class '{resolution_class_id}' is not registered."
            ) from error

    def get_disposition_class(
        self,
        disposition_class_id: str,
    ) -> CaseDispositionClassDefinition:
        try:
            return self._disposition_classes[disposition_class_id]
        except KeyError as error:
            raise ReviewResolutionRegistryError(
                f"Case disposition class '{disposition_class_id}' is not registered."
            ) from error

    def _load_resolution_classes(
        self,
        review_resolution_classes_path: Path,
    ) -> dict[str, ReviewResolutionClassDefinition]:
        content = json.loads(review_resolution_classes_path.read_text(encoding="utf-8"))
        resolution_classes: dict[str, ReviewResolutionClassDefinition] = {}
        for class_id, entry in content["review_resolution_classes"].items():
            self._contract_validator.validate_or_raise(
                "review_resolution_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="review_resolution_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["resolution_class_id"] != class_id:
                raise ReviewResolutionRegistryError(
                    f"Review resolution class key '{class_id}' must match resolution_class_id '{entry['resolution_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReviewResolutionRegistryError(
                    f"Review resolution class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["resolution_state"] not in _VALID_RESOLUTION_STATES:
                raise ReviewResolutionRegistryError(
                    f"Review resolution class '{class_id}' has invalid resolution_state '{entry['resolution_state']}'."
                )
            if entry["review_outcome"] not in _VALID_REVIEW_OUTCOMES:
                raise ReviewResolutionRegistryError(
                    f"Review resolution class '{class_id}' has invalid review_outcome '{entry['review_outcome']}'."
                )
            allowed_packet_statuses = tuple(entry["allowed_packet_statuses"])
            invalid_packet_statuses = set(allowed_packet_statuses).difference(_VALID_PACKET_STATUSES)
            if invalid_packet_statuses:
                raise ReviewResolutionRegistryError(
                    f"Review resolution class '{class_id}' has invalid allowed_packet_statuses {sorted(invalid_packet_statuses)}."
                )
            resolution_classes[class_id] = ReviewResolutionClassDefinition(
                resolution_class_id=entry["resolution_class_id"],
                description=entry["description"],
                resolution_state=entry["resolution_state"],
                review_outcome=entry["review_outcome"],
                disposition_class_id=entry["disposition_class_id"],
                allowed_packet_statuses=allowed_packet_statuses,
                required_resolution_fields=tuple(entry["required_resolution_fields"]),
                optional_resolution_fields=tuple(entry["optional_resolution_fields"]),
                required_audit_fields=tuple(entry["required_audit_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return resolution_classes

    def _load_disposition_classes(
        self,
        case_disposition_classes_path: Path,
    ) -> dict[str, CaseDispositionClassDefinition]:
        content = json.loads(case_disposition_classes_path.read_text(encoding="utf-8"))
        disposition_classes: dict[str, CaseDispositionClassDefinition] = {}
        for class_id, entry in content["case_disposition_classes"].items():
            self._contract_validator.validate_or_raise(
                "case_disposition_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="case_disposition_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["disposition_class_id"] != class_id:
                raise ReviewResolutionRegistryError(
                    f"Case disposition class key '{class_id}' must match disposition_class_id '{entry['disposition_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReviewResolutionRegistryError(
                    f"Case disposition class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["disposition_state"] not in _VALID_DISPOSITION_STATES:
                raise ReviewResolutionRegistryError(
                    f"Case disposition class '{class_id}' has invalid disposition_state '{entry['disposition_state']}'."
                )
            if entry["closure_state"] not in _VALID_CLOSURE_STATES:
                raise ReviewResolutionRegistryError(
                    f"Case disposition class '{class_id}' has invalid closure_state '{entry['closure_state']}'."
                )
            if entry["closure_quality"] not in _VALID_CLOSURE_QUALITIES:
                raise ReviewResolutionRegistryError(
                    f"Case disposition class '{class_id}' has invalid closure_quality '{entry['closure_quality']}'."
                )
            disposition_classes[class_id] = CaseDispositionClassDefinition(
                disposition_class_id=entry["disposition_class_id"],
                description=entry["description"],
                disposition_state=entry["disposition_state"],
                closure_state=entry["closure_state"],
                closure_quality=entry["closure_quality"],
                terminality=bool(entry["terminality"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
                reopen_reference=entry.get("reopen_reference"),
            )
        return disposition_classes

    def _validate_cross_registry_links(self) -> None:
        for resolution_class in self._resolution_classes.values():
            disposition_class = self._disposition_classes.get(resolution_class.disposition_class_id)
            if disposition_class is None:
                raise ReviewResolutionRegistryError(
                    f"Review resolution class '{resolution_class.resolution_class_id}' references unknown disposition_class_id '{resolution_class.disposition_class_id}'."
                )
            if disposition_class.status != "active":
                raise ReviewResolutionRegistryError(
                    f"Review resolution class '{resolution_class.resolution_class_id}' references inactive disposition class '{resolution_class.disposition_class_id}'."
                )
            if not resolution_class.required_resolution_fields:
                raise ReviewResolutionRegistryError(
                    f"Review resolution class '{resolution_class.resolution_class_id}' must declare at least one required_resolution_field."
                )
            if not resolution_class.required_audit_fields:
                raise ReviewResolutionRegistryError(
                    f"Review resolution class '{resolution_class.resolution_class_id}' must declare at least one required_audit_field."
                )