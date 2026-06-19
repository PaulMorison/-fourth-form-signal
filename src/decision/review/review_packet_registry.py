from __future__ import annotations

"""Registry-backed human review packet templates and reason classes.

Canon ownership:
- Owns governed packet-template identity and governed packet reason classes for
  review-only handoff construction.
- Does not execute review resolution, escalation workflow, recommendation
  meaning, or action-instruction meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_REVIEW_MODES = {"required", "optional"}
_VALID_PACKET_STATUSES = {"ready_for_handoff", "fallback_template_applied"}
_VALID_PACKET_SCOPES = {"case_review", "fallback_review"}
_VALID_HANDOFF_PURPOSES = {"review_only", "manual_triage"}


class ReviewPacketRegistryError(ValueError):
    """Base error for review-packet registry failures."""


@dataclass(frozen=True)
class ReviewReasonClassDefinition:
    reason_class: str
    description: str
    handoff_purpose: str
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ReviewPacketTemplateDefinition:
    packet_template_id: str
    semantic_scope: str
    router_rule_id: str
    transition_name: str
    route_name: str | None
    threshold_id: str | None
    review_mode: str
    reason_class: str
    packet_scope: str
    required_context_fields: tuple[str, ...]
    optional_context_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    handoff_channel: str
    packet_status: str
    status: str
    lineage: Mapping[str, str]


class ReviewPacketRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        router_rule_id: str,
        transition_name: str,
        route_name: str | None,
        review_mode: str,
        threshold_id: str | None,
    ) -> tuple[ReviewPacketTemplateDefinition, bool]:
        """Return the matching packet template and whether it was a fallback template."""

    def get_reason_class(self, reason_class: str) -> ReviewReasonClassDefinition:
        """Return the named review reason class."""


class JsonReviewPacketRegistry:
    """Loads packet templates and reason classes from checked-in registries."""

    def __init__(
        self,
        *,
        review_packet_templates_path: Path,
        review_reason_classes_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._reason_classes = self._load_reason_classes(review_reason_classes_path)
        self._packet_templates = self._load_packet_templates(review_packet_templates_path)
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        router_rule_id: str,
        transition_name: str,
        route_name: str | None,
        review_mode: str,
        threshold_id: str | None,
    ) -> tuple[ReviewPacketTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._packet_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.router_rule_id == router_rule_id
            and template.transition_name == transition_name
            and template.review_mode == review_mode
            and template.route_name == route_name
            and template.threshold_id == threshold_id
        )
        if exact_matches:
            return sorted(exact_matches, key=lambda template: template.packet_template_id)[0], False

        fallback_matches = tuple(
            template
            for template in self._packet_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.router_rule_id == router_rule_id
            and template.transition_name == transition_name
            and template.review_mode == review_mode
            and template.route_name == route_name
            and template.threshold_id is None
        )
        if fallback_matches:
            return sorted(fallback_matches, key=lambda template: template.packet_template_id)[0], True

        raise ReviewPacketRegistryError(
            "No governed review packet template applies to the review-trigger outcome "
            f"for router_rule_id='{router_rule_id}', transition_name='{transition_name}', "
            f"route_name='{route_name}', review_mode='{review_mode}', threshold_id='{threshold_id}'."
        )

    def get_reason_class(self, reason_class: str) -> ReviewReasonClassDefinition:
        try:
            return self._reason_classes[reason_class]
        except KeyError as error:
            raise ReviewPacketRegistryError(
                f"Review reason class '{reason_class}' is not registered."
            ) from error

    def _load_reason_classes(
        self,
        review_reason_classes_path: Path,
    ) -> dict[str, ReviewReasonClassDefinition]:
        content = json.loads(review_reason_classes_path.read_text(encoding="utf-8"))
        reason_classes: dict[str, ReviewReasonClassDefinition] = {}
        for reason_class_id, entry in content["review_reason_classes"].items():
            self._contract_validator.validate_or_raise(
                "review_reason_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="review_reason_class",
                entity_id=reason_class_id,
                emit_audit_events=False,
            )
            if entry["reason_class"] != reason_class_id:
                raise ReviewPacketRegistryError(
                    f"Review reason class key '{reason_class_id}' must match reason_class '{entry['reason_class']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReviewPacketRegistryError(
                    f"Review reason class '{reason_class_id}' has invalid status '{entry['status']}'."
                )
            if entry["handoff_purpose"] not in _VALID_HANDOFF_PURPOSES:
                raise ReviewPacketRegistryError(
                    f"Review reason class '{reason_class_id}' has invalid handoff_purpose '{entry['handoff_purpose']}'."
                )
            reason_classes[reason_class_id] = ReviewReasonClassDefinition(
                reason_class=entry["reason_class"],
                description=entry["description"],
                handoff_purpose=entry["handoff_purpose"],
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return reason_classes

    def _load_packet_templates(
        self,
        review_packet_templates_path: Path,
    ) -> tuple[ReviewPacketTemplateDefinition, ...]:
        content = json.loads(review_packet_templates_path.read_text(encoding="utf-8"))
        packet_templates: list[ReviewPacketTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["review_packet_templates"].items():
            self._contract_validator.validate_or_raise(
                "review_packet_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="review_packet_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["packet_template_id"] != template_id:
                raise ReviewPacketRegistryError(
                    f"Packet template key '{template_id}' must match packet_template_id '{entry['packet_template_id']}'."
                )
            if template_id in template_ids:
                raise ReviewPacketRegistryError(
                    f"Duplicate packet_template_id '{template_id}' found in review packet template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReviewPacketRegistryError(
                    f"Packet template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["review_mode"] not in _VALID_REVIEW_MODES:
                raise ReviewPacketRegistryError(
                    f"Packet template '{template_id}' has invalid review_mode '{entry['review_mode']}'."
                )
            if entry["packet_status"] not in _VALID_PACKET_STATUSES:
                raise ReviewPacketRegistryError(
                    f"Packet template '{template_id}' has invalid packet_status '{entry['packet_status']}'."
                )
            if entry["packet_scope"] not in _VALID_PACKET_SCOPES:
                raise ReviewPacketRegistryError(
                    f"Packet template '{template_id}' has invalid packet_scope '{entry['packet_scope']}'."
                )
            packet_templates.append(
                ReviewPacketTemplateDefinition(
                    packet_template_id=entry["packet_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    router_rule_id=entry["router_rule_id"],
                    transition_name=entry["transition_name"],
                    route_name=entry.get("route_name"),
                    threshold_id=entry.get("threshold_id"),
                    review_mode=entry["review_mode"],
                    reason_class=entry["reason_class"],
                    packet_scope=entry["packet_scope"],
                    required_context_fields=tuple(entry["required_context_fields"]),
                    optional_context_fields=tuple(entry["optional_context_fields"]),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    handoff_channel=entry["handoff_channel"],
                    packet_status=entry["packet_status"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                )
            )
            template_ids.add(template_id)
        return tuple(packet_templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._packet_templates:
            reason_class = self._reason_classes.get(template.reason_class)
            if reason_class is None:
                raise ReviewPacketRegistryError(
                    f"Packet template '{template.packet_template_id}' references unknown reason_class '{template.reason_class}'."
                )
            if reason_class.status != "active":
                raise ReviewPacketRegistryError(
                    f"Packet template '{template.packet_template_id}' references inactive reason_class '{template.reason_class}'."
                )
            if not template.required_context_fields:
                raise ReviewPacketRegistryError(
                    f"Packet template '{template.packet_template_id}' must declare at least one required_context_field."
                )
            if not template.required_audit_fields:
                raise ReviewPacketRegistryError(
                    f"Packet template '{template.packet_template_id}' must declare at least one required_audit_field."
                )
            if template.threshold_id is None and template.packet_status != "fallback_template_applied":
                raise ReviewPacketRegistryError(
                    f"Packet template '{template.packet_template_id}' omits threshold_id and must therefore declare packet_status 'fallback_template_applied'."
                )