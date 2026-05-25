from __future__ import annotations

"""Registry-backed policy-output classes and policy-output templates.

Canon ownership:
- Owns governed policy-output identity and template identity for bounded output
  objects emitted after legitimate recommendation records.
- Does not execute commitment issuance, action-instruction issuance, playbook
  execution, reopen handling, router meaning, or authority meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_BOUNDED_POLICY_POSTURES = {
    "policy_shaped_allowance",
    "policy_shaped_wait_boundary",
    "policy_shaped_simulation_requirement",
    "policy_shaped_information_requirement",
    "policy_shaped_escalation_boundary",
    "policy_shaped_suppression",
}
_VALID_ACTION_BOUNDARY_POSTURES = {"policy_shaped_non_instructional"}
_VALID_PROMOTION_SAFE_USE = {"promotion_safe_output"}
_VALID_POLICY_OUTPUT_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}


class PolicyOutputRegistryError(ValueError):
    """Base error for policy-output registry failures."""


@dataclass(frozen=True)
class PolicyOutputClassDefinition:
    policy_output_class_id: str
    description: str
    bounded_policy_posture: str
    action_boundary_posture: str
    promotion_safe_use: str
    allowed_recommendation_class_ids: tuple[str, ...]
    allowed_resolution_class_ids: tuple[str, ...]
    allowed_disposition_class_ids: tuple[str, ...]
    prohibited_context_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PolicyOutputTemplateDefinition:
    policy_output_template_id: str
    semantic_scope: str
    resolution_class_id: str
    disposition_class_id: str
    recommendation_class_id: str
    policy_output_class_id: str
    required_context_fields: tuple[str, ...]
    optional_context_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    policy_output_status: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PolicyOutputRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        resolution_class_id: str,
        disposition_class_id: str,
        recommendation_class_id: str,
        policy_output_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyOutputTemplateDefinition, bool]:
        """Return the matching policy-output template and fallback status."""

    def get_policy_output_class(
        self,
        policy_output_class_id: str,
    ) -> PolicyOutputClassDefinition:
        """Return the named policy-output class."""


class JsonPolicyOutputRegistry:
    """Loads policy-output classes and templates from checked-in registries."""

    def __init__(
        self,
        *,
        policy_output_classes_path: Path,
        policy_output_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._policy_output_classes = self._load_policy_output_classes(
            policy_output_classes_path
        )
        self._policy_output_templates = self._load_policy_output_templates(
            policy_output_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        resolution_class_id: str,
        disposition_class_id: str,
        recommendation_class_id: str,
        policy_output_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyOutputTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._policy_output_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.policy_output_class_id == policy_output_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.policy_output_template_id,
            )[0]
            return template, template.policy_output_status == "fallback_template_applied"

        generic_matches = tuple(
            template
            for template in self._policy_output_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.policy_output_class_id == policy_output_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.policy_output_template_id,
            )[0]
            return template, template.policy_output_status == "fallback_template_applied"

        raise PolicyOutputRegistryError(
            "No governed policy-output template applies to policy_output_class_id="
            f"'{policy_output_class_id}' for recommendation_class_id='{recommendation_class_id}', "
            f"resolution_class_id='{resolution_class_id}', disposition_class_id='{disposition_class_id}', "
            f"route_name='{route_name}'."
        )

    def get_policy_output_class(
        self,
        policy_output_class_id: str,
    ) -> PolicyOutputClassDefinition:
        try:
            return self._policy_output_classes[policy_output_class_id]
        except KeyError as error:
            raise PolicyOutputRegistryError(
                f"Policy output class '{policy_output_class_id}' is not registered."
            ) from error

    def _load_policy_output_classes(
        self,
        policy_output_classes_path: Path,
    ) -> dict[str, PolicyOutputClassDefinition]:
        content = json.loads(policy_output_classes_path.read_text(encoding="utf-8"))
        policy_output_classes: dict[str, PolicyOutputClassDefinition] = {}
        for class_id, entry in content["policy_output_classes"].items():
            self._contract_validator.validate_or_raise(
                "policy_output_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_output_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["policy_output_class_id"] != class_id:
                raise PolicyOutputRegistryError(
                    f"Policy output class key '{class_id}' must match policy_output_class_id '{entry['policy_output_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyOutputRegistryError(
                    f"Policy output class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["bounded_policy_posture"] not in _VALID_BOUNDED_POLICY_POSTURES:
                raise PolicyOutputRegistryError(
                    f"Policy output class '{class_id}' has invalid bounded_policy_posture '{entry['bounded_policy_posture']}'."
                )
            if entry["action_boundary_posture"] not in _VALID_ACTION_BOUNDARY_POSTURES:
                raise PolicyOutputRegistryError(
                    f"Policy output class '{class_id}' has invalid action_boundary_posture '{entry['action_boundary_posture']}'."
                )
            if entry["promotion_safe_use"] not in _VALID_PROMOTION_SAFE_USE:
                raise PolicyOutputRegistryError(
                    f"Policy output class '{class_id}' has invalid promotion_safe_use '{entry['promotion_safe_use']}'."
                )
            policy_output_classes[class_id] = PolicyOutputClassDefinition(
                policy_output_class_id=entry["policy_output_class_id"],
                description=entry["description"],
                bounded_policy_posture=entry["bounded_policy_posture"],
                action_boundary_posture=entry["action_boundary_posture"],
                promotion_safe_use=entry["promotion_safe_use"],
                allowed_recommendation_class_ids=tuple(
                    entry["allowed_recommendation_class_ids"]
                ),
                allowed_resolution_class_ids=tuple(entry["allowed_resolution_class_ids"]),
                allowed_disposition_class_ids=tuple(
                    entry["allowed_disposition_class_ids"]
                ),
                prohibited_context_fields=tuple(entry["prohibited_context_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return policy_output_classes

    def _load_policy_output_templates(
        self,
        policy_output_templates_path: Path,
    ) -> tuple[PolicyOutputTemplateDefinition, ...]:
        content = json.loads(policy_output_templates_path.read_text(encoding="utf-8"))
        policy_output_templates: list[PolicyOutputTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["policy_output_templates"].items():
            self._contract_validator.validate_or_raise(
                "policy_output_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_output_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["policy_output_template_id"] != template_id:
                raise PolicyOutputRegistryError(
                    f"Policy output template key '{template_id}' must match policy_output_template_id '{entry['policy_output_template_id']}'."
                )
            if template_id in template_ids:
                raise PolicyOutputRegistryError(
                    f"Duplicate policy_output_template_id '{template_id}' found in policy output template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["policy_output_status"] not in _VALID_POLICY_OUTPUT_STATUSES:
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template_id}' has invalid policy_output_status '{entry['policy_output_status']}'."
                )
            policy_output_templates.append(
                PolicyOutputTemplateDefinition(
                    policy_output_template_id=entry["policy_output_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    resolution_class_id=entry["resolution_class_id"],
                    disposition_class_id=entry["disposition_class_id"],
                    recommendation_class_id=entry["recommendation_class_id"],
                    policy_output_class_id=entry["policy_output_class_id"],
                    required_context_fields=tuple(entry["required_context_fields"]),
                    optional_context_fields=tuple(entry["optional_context_fields"]),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    policy_output_status=entry["policy_output_status"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(policy_output_templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._policy_output_templates:
            policy_output_class = self._policy_output_classes.get(
                template.policy_output_class_id
            )
            if policy_output_class is None:
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template.policy_output_template_id}' references unknown policy_output_class_id '{template.policy_output_class_id}'."
                )
            if policy_output_class.status != "active":
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template.policy_output_template_id}' references inactive policy output class '{template.policy_output_class_id}'."
                )
            if (
                template.recommendation_class_id
                not in policy_output_class.allowed_recommendation_class_ids
            ):
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template.policy_output_template_id}' uses recommendation_class_id '{template.recommendation_class_id}' outside policy output class '{template.policy_output_class_id}' allowances."
                )
            if (
                template.resolution_class_id
                not in policy_output_class.allowed_resolution_class_ids
            ):
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template.policy_output_template_id}' uses resolution_class_id '{template.resolution_class_id}' outside policy output class '{template.policy_output_class_id}' allowances."
                )
            if (
                template.disposition_class_id
                not in policy_output_class.allowed_disposition_class_ids
            ):
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template.policy_output_template_id}' uses disposition_class_id '{template.disposition_class_id}' outside policy output class '{template.policy_output_class_id}' allowances."
                )
            if not template.required_context_fields:
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template.policy_output_template_id}' must declare at least one required_context_field."
                )
            if not template.required_audit_fields:
                raise PolicyOutputRegistryError(
                    f"Policy output template '{template.policy_output_template_id}' must declare at least one required_audit_field."
                )
            if not policy_output_class.prohibited_context_fields:
                raise PolicyOutputRegistryError(
                    f"Policy output class '{policy_output_class.policy_output_class_id}' must declare at least one prohibited_context_field."
                )