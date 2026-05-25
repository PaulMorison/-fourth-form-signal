from __future__ import annotations

"""Registry-backed execution-request classes and execution-request templates.

Canon ownership:
- Owns governed execution-request identity and template identity for bounded
  execution requests emitted after legitimate action instructions.
- Does not execute requests, redefine action-instruction meaning, or absorb
  portfolio, policy, recommendation, review, router, or authority semantics.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_ACTION_BOUNDARY_POSTURES = {
    "request_ready_non_executing",
    "request_conditioned_non_executing",
    "request_hold_non_executing",
}
_VALID_EXECUTION_REQUEST_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}
_VALID_EXECUTION_REQUEST_READINESS = {
    "dispatch_ready",
    "dispatch_blocked_pending_authority",
    "dispatch_blocked_pending_prerequisite",
    "dispatch_blocked_pending_timing",
    "dispatch_prohibited",
    "request_incomplete",
}


class ExecutionRequestRegistryError(ValueError):
    """Base error for execution-request registry failures."""


@dataclass(frozen=True)
class ExecutionRequestClassDefinition:
    execution_request_class_id: str
    description: str
    action_boundary_posture: str
    allowed_action_instruction_class_ids: tuple[str, ...]
    prohibited_execution_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ExecutionRequestTemplateDefinition:
    execution_request_template_id: str
    semantic_scope: str
    resolution_class_id: str
    disposition_class_id: str
    recommendation_class_id: str
    policy_output_class_id: str
    portfolio_output_class_id: str
    action_instruction_class_id: str
    execution_request_class_id: str
    required_execution_request_fields: tuple[str, ...]
    optional_execution_request_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    execution_request_status: str
    execution_request_readiness: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class ExecutionRequestRegistry(Protocol):
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
        execution_request_class_id: str,
        route_name: str | None,
    ) -> tuple[ExecutionRequestTemplateDefinition, bool]:
        """Return the matching execution-request template and fallback status."""

    def get_execution_request_class(
        self,
        execution_request_class_id: str,
    ) -> ExecutionRequestClassDefinition:
        """Return the named execution-request class."""


class JsonExecutionRequestRegistry:
    """Loads execution-request classes and templates from checked-in registries."""

    def __init__(
        self,
        *,
        execution_request_classes_path: Path,
        execution_request_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._execution_request_classes = self._load_execution_request_classes(
            execution_request_classes_path
        )
        self._execution_request_templates = self._load_execution_request_templates(
            execution_request_templates_path
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
        execution_request_class_id: str,
        route_name: str | None,
    ) -> tuple[ExecutionRequestTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._execution_request_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.policy_output_class_id == policy_output_class_id
            and template.portfolio_output_class_id == portfolio_output_class_id
            and template.action_instruction_class_id == action_instruction_class_id
            and template.execution_request_class_id == execution_request_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.execution_request_template_id,
            )[0]
            return template, template.execution_request_status == "fallback_template_applied"

        generic_matches = tuple(
            template
            for template in self._execution_request_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.policy_output_class_id == policy_output_class_id
            and template.portfolio_output_class_id == portfolio_output_class_id
            and template.action_instruction_class_id == action_instruction_class_id
            and template.execution_request_class_id == execution_request_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.execution_request_template_id,
            )[0]
            return template, template.execution_request_status == "fallback_template_applied"

        raise ExecutionRequestRegistryError(
            "No governed execution-request template applies to execution_request_class_id="
            f"'{execution_request_class_id}' for action_instruction_class_id='{action_instruction_class_id}', "
            f"portfolio_output_class_id='{portfolio_output_class_id}', policy_output_class_id='{policy_output_class_id}', "
            f"recommendation_class_id='{recommendation_class_id}', resolution_class_id='{resolution_class_id}', "
            f"disposition_class_id='{disposition_class_id}', route_name='{route_name}'."
        )

    def get_execution_request_class(
        self,
        execution_request_class_id: str,
    ) -> ExecutionRequestClassDefinition:
        try:
            return self._execution_request_classes[execution_request_class_id]
        except KeyError as error:
            raise ExecutionRequestRegistryError(
                f"Execution request class '{execution_request_class_id}' is not registered."
            ) from error

    def _load_execution_request_classes(
        self,
        execution_request_classes_path: Path,
    ) -> dict[str, ExecutionRequestClassDefinition]:
        content = json.loads(execution_request_classes_path.read_text(encoding="utf-8"))
        execution_request_classes: dict[str, ExecutionRequestClassDefinition] = {}
        for class_id, entry in content["execution_request_classes"].items():
            self._contract_validator.validate_or_raise(
                "execution_request_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="execution_request_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["execution_request_class_id"] != class_id:
                raise ExecutionRequestRegistryError(
                    f"Execution request class key '{class_id}' must match execution_request_class_id '{entry['execution_request_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ExecutionRequestRegistryError(
                    f"Execution request class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["action_boundary_posture"] not in _VALID_ACTION_BOUNDARY_POSTURES:
                raise ExecutionRequestRegistryError(
                    f"Execution request class '{class_id}' has invalid action_boundary_posture '{entry['action_boundary_posture']}'."
                )
            execution_request_classes[class_id] = ExecutionRequestClassDefinition(
                execution_request_class_id=entry["execution_request_class_id"],
                description=entry["description"],
                action_boundary_posture=entry["action_boundary_posture"],
                allowed_action_instruction_class_ids=tuple(
                    entry["allowed_action_instruction_class_ids"]
                ),
                prohibited_execution_fields=tuple(entry["prohibited_execution_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return execution_request_classes

    def _load_execution_request_templates(
        self,
        execution_request_templates_path: Path,
    ) -> tuple[ExecutionRequestTemplateDefinition, ...]:
        content = json.loads(execution_request_templates_path.read_text(encoding="utf-8"))
        execution_request_templates: list[ExecutionRequestTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["execution_request_templates"].items():
            self._contract_validator.validate_or_raise(
                "execution_request_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="execution_request_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["execution_request_template_id"] != template_id:
                raise ExecutionRequestRegistryError(
                    f"Execution request template key '{template_id}' must match execution_request_template_id '{entry['execution_request_template_id']}'."
                )
            if template_id in template_ids:
                raise ExecutionRequestRegistryError(
                    f"Duplicate execution_request_template_id '{template_id}' found in execution request template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ExecutionRequestRegistryError(
                    f"Execution request template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["execution_request_status"] not in _VALID_EXECUTION_REQUEST_STATUSES:
                raise ExecutionRequestRegistryError(
                    f"Execution request template '{template_id}' has invalid execution_request_status '{entry['execution_request_status']}'."
                )
            if entry["execution_request_readiness"] not in _VALID_EXECUTION_REQUEST_READINESS:
                raise ExecutionRequestRegistryError(
                    f"Execution request template '{template_id}' has invalid execution_request_readiness '{entry['execution_request_readiness']}'."
                )
            execution_request_templates.append(
                ExecutionRequestTemplateDefinition(
                    execution_request_template_id=entry["execution_request_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    resolution_class_id=entry["resolution_class_id"],
                    disposition_class_id=entry["disposition_class_id"],
                    recommendation_class_id=entry["recommendation_class_id"],
                    policy_output_class_id=entry["policy_output_class_id"],
                    portfolio_output_class_id=entry["portfolio_output_class_id"],
                    action_instruction_class_id=entry["action_instruction_class_id"],
                    execution_request_class_id=entry["execution_request_class_id"],
                    required_execution_request_fields=tuple(
                        entry["required_execution_request_fields"]
                    ),
                    optional_execution_request_fields=tuple(
                        entry["optional_execution_request_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    execution_request_status=entry["execution_request_status"],
                    execution_request_readiness=entry["execution_request_readiness"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(execution_request_templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._execution_request_templates:
            execution_request_class = self._execution_request_classes.get(
                template.execution_request_class_id
            )
            if execution_request_class is None:
                raise ExecutionRequestRegistryError(
                    f"Execution request template '{template.execution_request_template_id}' references unknown execution_request_class_id '{template.execution_request_class_id}'."
                )
            if execution_request_class.status != "active":
                raise ExecutionRequestRegistryError(
                    f"Execution request template '{template.execution_request_template_id}' references inactive execution request class '{template.execution_request_class_id}'."
                )
            if (
                template.action_instruction_class_id
                not in execution_request_class.allowed_action_instruction_class_ids
            ):
                raise ExecutionRequestRegistryError(
                    f"Execution request template '{template.execution_request_template_id}' uses action_instruction_class_id '{template.action_instruction_class_id}' outside execution request class '{template.execution_request_class_id}' allowances."
                )
            if not template.required_execution_request_fields:
                raise ExecutionRequestRegistryError(
                    f"Execution request template '{template.execution_request_template_id}' must declare at least one required_execution_request_field."
                )
            if not template.required_audit_fields:
                raise ExecutionRequestRegistryError(
                    f"Execution request template '{template.execution_request_template_id}' must declare at least one required_audit_field."
                )
            if not execution_request_class.prohibited_execution_fields:
                raise ExecutionRequestRegistryError(
                    f"Execution request class '{execution_request_class.execution_request_class_id}' must declare at least one prohibited_execution_field."
                )