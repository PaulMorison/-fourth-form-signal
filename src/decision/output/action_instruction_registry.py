from __future__ import annotations

"""Registry-backed action-instruction classes and action-instruction templates.

Canon ownership:
- Owns governed action-instruction identity and template identity for bounded
  action instructions emitted after legitimate portfolio outputs.
- Does not execute actions, generate commitment meaning, or absorb portfolio,
  policy, recommendation, review, or authority semantics.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_BOUNDED_ACTION_POSTURES = {
    "direct_action_instruction",
    "prerequisite_bounded_instruction",
    "suppression_hold_instruction",
}
_VALID_EXECUTION_BOUNDARY_POSTURES = {"instruction_not_executed"}
_VALID_PROMOTION_SAFE_USE = {"promotion_safe_instruction"}
_VALID_ACTION_INSTRUCTION_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}
_VALID_INSTRUCTION_STATUSES = {
    "instruction_permitted",
    "instruction_prohibited",
    "instruction_conditionally_permitted",
    "instruction_issued",
    "instruction_invalidated",
    "instruction_blocked_pending_authority",
    "instruction_blocked_pending_prerequisite",
    "instruction_blocked_pending_timing",
    "executable_instruction_ready",
    "unauthorized_instruction_state",
}


class ActionInstructionRegistryError(ValueError):
    """Base error for action-instruction registry failures."""


@dataclass(frozen=True)
class ActionInstructionClassDefinition:
    action_instruction_class_id: str
    description: str
    bounded_action_posture: str
    execution_boundary_posture: str
    promotion_safe_use: str
    allowed_portfolio_output_class_ids: tuple[str, ...]
    allowed_policy_output_class_ids: tuple[str, ...]
    allowed_recommendation_class_ids: tuple[str, ...]
    allowed_resolution_class_ids: tuple[str, ...]
    allowed_disposition_class_ids: tuple[str, ...]
    prohibited_execution_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ActionInstructionTemplateDefinition:
    action_instruction_template_id: str
    semantic_scope: str
    resolution_class_id: str
    disposition_class_id: str
    recommendation_class_id: str
    policy_output_class_id: str
    portfolio_output_class_id: str
    action_instruction_class_id: str
    required_instruction_fields: tuple[str, ...]
    optional_instruction_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    action_instruction_status: str
    instruction_status: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class ActionInstructionRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        resolution_class_id: str,
        disposition_class_id: str,
        recommendation_class_id: str,
        policy_output_class_id: str,
        portfolio_output_class_id: str,
        action_instruction_class_id: str,
        route_name: str | None,
    ) -> tuple[ActionInstructionTemplateDefinition, bool]:
        """Return the matching action-instruction template and fallback status."""

    def get_action_instruction_class(
        self,
        action_instruction_class_id: str,
    ) -> ActionInstructionClassDefinition:
        """Return the named action-instruction class."""


class JsonActionInstructionRegistry:
    """Loads action-instruction classes and templates from checked-in registries."""

    def __init__(
        self,
        *,
        action_instruction_classes_path: Path,
        action_instruction_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._action_instruction_classes = self._load_action_instruction_classes(
            action_instruction_classes_path
        )
        self._action_instruction_templates = self._load_action_instruction_templates(
            action_instruction_templates_path
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
        portfolio_output_class_id: str,
        action_instruction_class_id: str,
        route_name: str | None,
    ) -> tuple[ActionInstructionTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._action_instruction_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.policy_output_class_id == policy_output_class_id
            and template.portfolio_output_class_id == portfolio_output_class_id
            and template.action_instruction_class_id == action_instruction_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.action_instruction_template_id,
            )[0]
            return template, template.action_instruction_status == "fallback_template_applied"

        generic_matches = tuple(
            template
            for template in self._action_instruction_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.policy_output_class_id == policy_output_class_id
            and template.portfolio_output_class_id == portfolio_output_class_id
            and template.action_instruction_class_id == action_instruction_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.action_instruction_template_id,
            )[0]
            return template, template.action_instruction_status == "fallback_template_applied"

        raise ActionInstructionRegistryError(
            "No governed action-instruction template applies to action_instruction_class_id="
            f"'{action_instruction_class_id}' for portfolio_output_class_id='{portfolio_output_class_id}', "
            f"policy_output_class_id='{policy_output_class_id}', recommendation_class_id='{recommendation_class_id}', "
            f"resolution_class_id='{resolution_class_id}', disposition_class_id='{disposition_class_id}', route_name='{route_name}'."
        )

    def get_action_instruction_class(
        self,
        action_instruction_class_id: str,
    ) -> ActionInstructionClassDefinition:
        try:
            return self._action_instruction_classes[action_instruction_class_id]
        except KeyError as error:
            raise ActionInstructionRegistryError(
                f"Action instruction class '{action_instruction_class_id}' is not registered."
            ) from error

    def _load_action_instruction_classes(
        self,
        action_instruction_classes_path: Path,
    ) -> dict[str, ActionInstructionClassDefinition]:
        content = json.loads(action_instruction_classes_path.read_text(encoding="utf-8"))
        action_instruction_classes: dict[str, ActionInstructionClassDefinition] = {}
        for class_id, entry in content["action_instruction_classes"].items():
            self._contract_validator.validate_or_raise(
                "action_instruction_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="action_instruction_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["action_instruction_class_id"] != class_id:
                raise ActionInstructionRegistryError(
                    f"Action instruction class key '{class_id}' must match action_instruction_class_id '{entry['action_instruction_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ActionInstructionRegistryError(
                    f"Action instruction class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["bounded_action_posture"] not in _VALID_BOUNDED_ACTION_POSTURES:
                raise ActionInstructionRegistryError(
                    f"Action instruction class '{class_id}' has invalid bounded_action_posture '{entry['bounded_action_posture']}'."
                )
            if entry["execution_boundary_posture"] not in _VALID_EXECUTION_BOUNDARY_POSTURES:
                raise ActionInstructionRegistryError(
                    f"Action instruction class '{class_id}' has invalid execution_boundary_posture '{entry['execution_boundary_posture']}'."
                )
            if entry["promotion_safe_use"] not in _VALID_PROMOTION_SAFE_USE:
                raise ActionInstructionRegistryError(
                    f"Action instruction class '{class_id}' has invalid promotion_safe_use '{entry['promotion_safe_use']}'."
                )
            action_instruction_classes[class_id] = ActionInstructionClassDefinition(
                action_instruction_class_id=entry["action_instruction_class_id"],
                description=entry["description"],
                bounded_action_posture=entry["bounded_action_posture"],
                execution_boundary_posture=entry["execution_boundary_posture"],
                promotion_safe_use=entry["promotion_safe_use"],
                allowed_portfolio_output_class_ids=tuple(
                    entry["allowed_portfolio_output_class_ids"]
                ),
                allowed_policy_output_class_ids=tuple(
                    entry["allowed_policy_output_class_ids"]
                ),
                allowed_recommendation_class_ids=tuple(
                    entry["allowed_recommendation_class_ids"]
                ),
                allowed_resolution_class_ids=tuple(entry["allowed_resolution_class_ids"]),
                allowed_disposition_class_ids=tuple(
                    entry["allowed_disposition_class_ids"]
                ),
                prohibited_execution_fields=tuple(entry["prohibited_execution_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return action_instruction_classes

    def _load_action_instruction_templates(
        self,
        action_instruction_templates_path: Path,
    ) -> tuple[ActionInstructionTemplateDefinition, ...]:
        content = json.loads(action_instruction_templates_path.read_text(encoding="utf-8"))
        action_instruction_templates: list[ActionInstructionTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["action_instruction_templates"].items():
            self._contract_validator.validate_or_raise(
                "action_instruction_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="action_instruction_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["action_instruction_template_id"] != template_id:
                raise ActionInstructionRegistryError(
                    f"Action instruction template key '{template_id}' must match action_instruction_template_id '{entry['action_instruction_template_id']}'."
                )
            if template_id in template_ids:
                raise ActionInstructionRegistryError(
                    f"Duplicate action_instruction_template_id '{template_id}' found in action instruction template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["action_instruction_status"] not in _VALID_ACTION_INSTRUCTION_STATUSES:
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template_id}' has invalid action_instruction_status '{entry['action_instruction_status']}'."
                )
            if entry["instruction_status"] not in _VALID_INSTRUCTION_STATUSES:
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template_id}' has invalid instruction_status '{entry['instruction_status']}'."
                )
            action_instruction_templates.append(
                ActionInstructionTemplateDefinition(
                    action_instruction_template_id=entry["action_instruction_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    resolution_class_id=entry["resolution_class_id"],
                    disposition_class_id=entry["disposition_class_id"],
                    recommendation_class_id=entry["recommendation_class_id"],
                    policy_output_class_id=entry["policy_output_class_id"],
                    portfolio_output_class_id=entry["portfolio_output_class_id"],
                    action_instruction_class_id=entry["action_instruction_class_id"],
                    required_instruction_fields=tuple(entry["required_instruction_fields"]),
                    optional_instruction_fields=tuple(entry["optional_instruction_fields"]),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    action_instruction_status=entry["action_instruction_status"],
                    instruction_status=entry["instruction_status"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(action_instruction_templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._action_instruction_templates:
            action_instruction_class = self._action_instruction_classes.get(
                template.action_instruction_class_id
            )
            if action_instruction_class is None:
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' references unknown action_instruction_class_id '{template.action_instruction_class_id}'."
                )
            if action_instruction_class.status != "active":
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' references inactive action instruction class '{template.action_instruction_class_id}'."
                )
            if (
                template.portfolio_output_class_id
                not in action_instruction_class.allowed_portfolio_output_class_ids
            ):
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' uses portfolio_output_class_id '{template.portfolio_output_class_id}' outside action instruction class '{template.action_instruction_class_id}' allowances."
                )
            if (
                template.policy_output_class_id
                not in action_instruction_class.allowed_policy_output_class_ids
            ):
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' uses policy_output_class_id '{template.policy_output_class_id}' outside action instruction class '{template.action_instruction_class_id}' allowances."
                )
            if (
                template.recommendation_class_id
                not in action_instruction_class.allowed_recommendation_class_ids
            ):
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' uses recommendation_class_id '{template.recommendation_class_id}' outside action instruction class '{template.action_instruction_class_id}' allowances."
                )
            if (
                template.resolution_class_id
                not in action_instruction_class.allowed_resolution_class_ids
            ):
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' uses resolution_class_id '{template.resolution_class_id}' outside action instruction class '{template.action_instruction_class_id}' allowances."
                )
            if (
                template.disposition_class_id
                not in action_instruction_class.allowed_disposition_class_ids
            ):
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' uses disposition_class_id '{template.disposition_class_id}' outside action instruction class '{template.action_instruction_class_id}' allowances."
                )
            if not template.required_instruction_fields:
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' must declare at least one required_instruction_field."
                )
            if not template.required_audit_fields:
                raise ActionInstructionRegistryError(
                    f"Action instruction template '{template.action_instruction_template_id}' must declare at least one required_audit_field."
                )
            if not action_instruction_class.prohibited_execution_fields:
                raise ActionInstructionRegistryError(
                    f"Action instruction class '{action_instruction_class.action_instruction_class_id}' must declare at least one prohibited_execution_field."
                )