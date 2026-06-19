from __future__ import annotations

"""Registry-backed recommendation classes and recommendation templates.

Canon ownership:
- Owns governed recommendation-class identity and template identity for
  advisory recommendation records emitted after legitimate review resolution.
- Does not execute commitment issuance, action-instruction issuance, playbook
  execution, policy-output generation, reopen handling, or router meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_ACTION_CLASSES = {
    "recommend_act_now",
    "recommend_wait",
    "recommend_simulate_first",
    "recommend_gather_more_information",
    "escalate_for_review",
    "abstain_from_strong_recommendation",
}
_VALID_ADVISORY_POSTURES = {"advisory_only"}
_VALID_COMMITMENT_READINESS = {"non_committable", "commitment_review_ready"}
_VALID_RECOMMENDATION_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}


class RecommendationRegistryError(ValueError):
    """Base error for recommendation registry failures."""


@dataclass(frozen=True)
class RecommendationClassDefinition:
    recommendation_class_id: str
    description: str
    action_class: str
    advisory_posture: str
    commitment_readiness: str
    allowed_resolution_class_ids: tuple[str, ...]
    allowed_disposition_class_ids: tuple[str, ...]
    prohibited_context_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class RecommendationTemplateDefinition:
    recommendation_template_id: str
    semantic_scope: str
    resolution_class_id: str
    disposition_class_id: str
    recommendation_class_id: str
    required_context_fields: tuple[str, ...]
    optional_context_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    recommendation_status: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class RecommendationRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        resolution_class_id: str,
        disposition_class_id: str,
        recommendation_class_id: str,
        route_name: str | None,
    ) -> tuple[RecommendationTemplateDefinition, bool]:
        """Return the matching recommendation template and fallback status."""

    def get_recommendation_class(
        self,
        recommendation_class_id: str,
    ) -> RecommendationClassDefinition:
        """Return the named recommendation class."""


class JsonRecommendationRegistry:
    """Loads recommendation classes and templates from checked-in registries."""

    def __init__(
        self,
        *,
        recommendation_classes_path: Path,
        recommendation_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._recommendation_classes = self._load_recommendation_classes(
            recommendation_classes_path
        )
        self._recommendation_templates = self._load_recommendation_templates(
            recommendation_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        resolution_class_id: str,
        disposition_class_id: str,
        recommendation_class_id: str,
        route_name: str | None,
    ) -> tuple[RecommendationTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._recommendation_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.recommendation_template_id,
            )[0]
            return template, template.recommendation_status == "fallback_template_applied"

        generic_matches = tuple(
            template
            for template in self._recommendation_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.recommendation_template_id,
            )[0]
            return template, template.recommendation_status == "fallback_template_applied"

        raise RecommendationRegistryError(
            "No governed recommendation template applies to recommendation_class_id="
            f"'{recommendation_class_id}' for resolution_class_id='{resolution_class_id}', "
            f"disposition_class_id='{disposition_class_id}', route_name='{route_name}'."
        )

    def get_recommendation_class(
        self,
        recommendation_class_id: str,
    ) -> RecommendationClassDefinition:
        try:
            return self._recommendation_classes[recommendation_class_id]
        except KeyError as error:
            raise RecommendationRegistryError(
                f"Recommendation class '{recommendation_class_id}' is not registered."
            ) from error

    def _load_recommendation_classes(
        self,
        recommendation_classes_path: Path,
    ) -> dict[str, RecommendationClassDefinition]:
        content = json.loads(recommendation_classes_path.read_text(encoding="utf-8"))
        recommendation_classes: dict[str, RecommendationClassDefinition] = {}
        for class_id, entry in content["recommendation_classes"].items():
            self._contract_validator.validate_or_raise(
                "recommendation_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="recommendation_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["recommendation_class_id"] != class_id:
                raise RecommendationRegistryError(
                    f"Recommendation class key '{class_id}' must match recommendation_class_id '{entry['recommendation_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise RecommendationRegistryError(
                    f"Recommendation class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["action_class"] not in _VALID_ACTION_CLASSES:
                raise RecommendationRegistryError(
                    f"Recommendation class '{class_id}' has invalid action_class '{entry['action_class']}'."
                )
            if entry["advisory_posture"] not in _VALID_ADVISORY_POSTURES:
                raise RecommendationRegistryError(
                    f"Recommendation class '{class_id}' has invalid advisory_posture '{entry['advisory_posture']}'."
                )
            if entry["commitment_readiness"] not in _VALID_COMMITMENT_READINESS:
                raise RecommendationRegistryError(
                    f"Recommendation class '{class_id}' has invalid commitment_readiness '{entry['commitment_readiness']}'."
                )
            recommendation_classes[class_id] = RecommendationClassDefinition(
                recommendation_class_id=entry["recommendation_class_id"],
                description=entry["description"],
                action_class=entry["action_class"],
                advisory_posture=entry["advisory_posture"],
                commitment_readiness=entry["commitment_readiness"],
                allowed_resolution_class_ids=tuple(entry["allowed_resolution_class_ids"]),
                allowed_disposition_class_ids=tuple(entry["allowed_disposition_class_ids"]),
                prohibited_context_fields=tuple(entry["prohibited_context_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return recommendation_classes

    def _load_recommendation_templates(
        self,
        recommendation_templates_path: Path,
    ) -> tuple[RecommendationTemplateDefinition, ...]:
        content = json.loads(recommendation_templates_path.read_text(encoding="utf-8"))
        recommendation_templates: list[RecommendationTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["recommendation_templates"].items():
            self._contract_validator.validate_or_raise(
                "recommendation_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="recommendation_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["recommendation_template_id"] != template_id:
                raise RecommendationRegistryError(
                    f"Recommendation template key '{template_id}' must match recommendation_template_id '{entry['recommendation_template_id']}'."
                )
            if template_id in template_ids:
                raise RecommendationRegistryError(
                    f"Duplicate recommendation_template_id '{template_id}' found in recommendation template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise RecommendationRegistryError(
                    f"Recommendation template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["recommendation_status"] not in _VALID_RECOMMENDATION_STATUSES:
                raise RecommendationRegistryError(
                    f"Recommendation template '{template_id}' has invalid recommendation_status '{entry['recommendation_status']}'."
                )
            recommendation_templates.append(
                RecommendationTemplateDefinition(
                    recommendation_template_id=entry["recommendation_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    resolution_class_id=entry["resolution_class_id"],
                    disposition_class_id=entry["disposition_class_id"],
                    recommendation_class_id=entry["recommendation_class_id"],
                    required_context_fields=tuple(entry["required_context_fields"]),
                    optional_context_fields=tuple(entry["optional_context_fields"]),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    recommendation_status=entry["recommendation_status"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(recommendation_templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._recommendation_templates:
            recommendation_class = self._recommendation_classes.get(
                template.recommendation_class_id
            )
            if recommendation_class is None:
                raise RecommendationRegistryError(
                    f"Recommendation template '{template.recommendation_template_id}' references unknown recommendation_class_id '{template.recommendation_class_id}'."
                )
            if recommendation_class.status != "active":
                raise RecommendationRegistryError(
                    f"Recommendation template '{template.recommendation_template_id}' references inactive recommendation class '{template.recommendation_class_id}'."
                )
            if template.resolution_class_id not in recommendation_class.allowed_resolution_class_ids:
                raise RecommendationRegistryError(
                    f"Recommendation template '{template.recommendation_template_id}' uses resolution_class_id '{template.resolution_class_id}' outside recommendation class '{template.recommendation_class_id}' allowances."
                )
            if (
                template.disposition_class_id
                not in recommendation_class.allowed_disposition_class_ids
            ):
                raise RecommendationRegistryError(
                    f"Recommendation template '{template.recommendation_template_id}' uses disposition_class_id '{template.disposition_class_id}' outside recommendation class '{template.recommendation_class_id}' allowances."
                )
            if not template.required_context_fields:
                raise RecommendationRegistryError(
                    f"Recommendation template '{template.recommendation_template_id}' must declare at least one required_context_field."
                )
            if not template.required_audit_fields:
                raise RecommendationRegistryError(
                    f"Recommendation template '{template.recommendation_template_id}' must declare at least one required_audit_field."
                )
            if not recommendation_class.prohibited_context_fields:
                raise RecommendationRegistryError(
                    f"Recommendation class '{recommendation_class.recommendation_class_id}' must declare at least one prohibited_context_field."
                )