from __future__ import annotations

"""Registry-backed execution-dispatch boundary classes and templates.

Canon ownership:
- Owns governed execution-dispatch boundary identity and template identity for
  bounded dispatch-boundary records emitted after legitimate execution requests.
- Does not execute requests, place broker or venue work, or absorb execution
  outcome, reopen, or reinstatement semantics.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_DISPATCH_BOUNDARY_POSTURES = {
    "dispatch_boundary_ready_non_executing",
    "dispatch_boundary_conditioned_non_executing",
    "dispatch_boundary_hold_non_executing",
}
_VALID_EXECUTION_DISPATCH_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}
_VALID_EXECUTION_DISPATCH_READINESS = {
    "dispatch_boundary_ready",
    "dispatch_boundary_blocked_pending_authority",
    "dispatch_boundary_blocked_pending_prerequisite",
    "dispatch_boundary_blocked_pending_timing",
    "dispatch_boundary_prohibited",
    "dispatch_boundary_incomplete",
}


class ExecutionDispatchRegistryError(ValueError):
    """Base error for execution-dispatch registry failures."""


@dataclass(frozen=True)
class ExecutionDispatchClassDefinition:
    execution_dispatch_class_id: str
    description: str
    dispatch_boundary_posture: str
    allowed_execution_request_class_ids: tuple[str, ...]
    prohibited_dispatch_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ExecutionDispatchTemplateDefinition:
    execution_dispatch_template_id: str
    semantic_scope: str
    execution_request_class_id: str
    execution_dispatch_class_id: str
    required_execution_dispatch_fields: tuple[str, ...]
    optional_execution_dispatch_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    execution_dispatch_status: str
    execution_dispatch_readiness: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class ExecutionDispatchRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        execution_request_class_id: str,
        execution_dispatch_class_id: str,
        route_name: str | None,
    ) -> tuple[ExecutionDispatchTemplateDefinition, bool]:
        """Return the matching execution-dispatch template and fallback status."""

    def get_execution_dispatch_class(
        self,
        execution_dispatch_class_id: str,
    ) -> ExecutionDispatchClassDefinition:
        """Return the named execution-dispatch class."""


class JsonExecutionDispatchRegistry:
    """Loads execution-dispatch classes and templates from checked-in registries."""

    def __init__(
        self,
        *,
        execution_dispatch_classes_path: Path,
        execution_dispatch_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._execution_dispatch_classes = self._load_execution_dispatch_classes(
            execution_dispatch_classes_path
        )
        self._execution_dispatch_templates = self._load_execution_dispatch_templates(
            execution_dispatch_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        execution_request_class_id: str,
        execution_dispatch_class_id: str,
        route_name: str | None,
    ) -> tuple[ExecutionDispatchTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._execution_dispatch_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.execution_request_class_id == execution_request_class_id
            and template.execution_dispatch_class_id == execution_dispatch_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.execution_dispatch_template_id,
            )[0]
            return template, template.execution_dispatch_status == "fallback_template_applied"

        generic_matches = tuple(
            template
            for template in self._execution_dispatch_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.execution_request_class_id == execution_request_class_id
            and template.execution_dispatch_class_id == execution_dispatch_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.execution_dispatch_template_id,
            )[0]
            return template, template.execution_dispatch_status == "fallback_template_applied"

        raise ExecutionDispatchRegistryError(
            "No governed execution-dispatch template applies to execution_dispatch_class_id="
            f"'{execution_dispatch_class_id}' for execution_request_class_id='{execution_request_class_id}' "
            f"and route_name='{route_name}'."
        )

    def get_execution_dispatch_class(
        self,
        execution_dispatch_class_id: str,
    ) -> ExecutionDispatchClassDefinition:
        try:
            return self._execution_dispatch_classes[execution_dispatch_class_id]
        except KeyError as error:
            raise ExecutionDispatchRegistryError(
                f"Execution dispatch class '{execution_dispatch_class_id}' is not registered."
            ) from error

    def _load_execution_dispatch_classes(
        self,
        execution_dispatch_classes_path: Path,
    ) -> dict[str, ExecutionDispatchClassDefinition]:
        content = json.loads(execution_dispatch_classes_path.read_text(encoding="utf-8"))
        execution_dispatch_classes: dict[str, ExecutionDispatchClassDefinition] = {}
        for class_id, entry in content["execution_dispatch_classes"].items():
            self._contract_validator.validate_or_raise(
                "execution_dispatch_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="execution_dispatch_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["execution_dispatch_class_id"] != class_id:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch class key '{class_id}' must match execution_dispatch_class_id '{entry['execution_dispatch_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["dispatch_boundary_posture"] not in _VALID_DISPATCH_BOUNDARY_POSTURES:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch class '{class_id}' has invalid dispatch_boundary_posture '{entry['dispatch_boundary_posture']}'."
                )
            execution_dispatch_classes[class_id] = ExecutionDispatchClassDefinition(
                execution_dispatch_class_id=entry["execution_dispatch_class_id"],
                description=entry["description"],
                dispatch_boundary_posture=entry["dispatch_boundary_posture"],
                allowed_execution_request_class_ids=tuple(
                    entry["allowed_execution_request_class_ids"]
                ),
                prohibited_dispatch_fields=tuple(entry["prohibited_dispatch_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return execution_dispatch_classes

    def _load_execution_dispatch_templates(
        self,
        execution_dispatch_templates_path: Path,
    ) -> tuple[ExecutionDispatchTemplateDefinition, ...]:
        content = json.loads(execution_dispatch_templates_path.read_text(encoding="utf-8"))
        execution_dispatch_templates: list[ExecutionDispatchTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["execution_dispatch_templates"].items():
            self._contract_validator.validate_or_raise(
                "execution_dispatch_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="execution_dispatch_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["execution_dispatch_template_id"] != template_id:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template key '{template_id}' must match execution_dispatch_template_id '{entry['execution_dispatch_template_id']}'."
                )
            if template_id in template_ids:
                raise ExecutionDispatchRegistryError(
                    f"Duplicate execution_dispatch_template_id '{template_id}' found in execution dispatch template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["execution_dispatch_status"] not in _VALID_EXECUTION_DISPATCH_STATUSES:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template '{template_id}' has invalid execution_dispatch_status '{entry['execution_dispatch_status']}'."
                )
            if (
                entry["execution_dispatch_readiness"]
                not in _VALID_EXECUTION_DISPATCH_READINESS
            ):
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template '{template_id}' has invalid execution_dispatch_readiness '{entry['execution_dispatch_readiness']}'."
                )
            execution_dispatch_templates.append(
                ExecutionDispatchTemplateDefinition(
                    execution_dispatch_template_id=entry["execution_dispatch_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    execution_request_class_id=entry["execution_request_class_id"],
                    execution_dispatch_class_id=entry["execution_dispatch_class_id"],
                    required_execution_dispatch_fields=tuple(
                        entry["required_execution_dispatch_fields"]
                    ),
                    optional_execution_dispatch_fields=tuple(
                        entry["optional_execution_dispatch_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    execution_dispatch_status=entry["execution_dispatch_status"],
                    execution_dispatch_readiness=entry["execution_dispatch_readiness"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(execution_dispatch_templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._execution_dispatch_templates:
            execution_dispatch_class = self._execution_dispatch_classes.get(
                template.execution_dispatch_class_id
            )
            if execution_dispatch_class is None:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template '{template.execution_dispatch_template_id}' references unknown execution_dispatch_class_id '{template.execution_dispatch_class_id}'."
                )
            if execution_dispatch_class.status != "active":
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template '{template.execution_dispatch_template_id}' references inactive execution dispatch class '{template.execution_dispatch_class_id}'."
                )
            if (
                template.execution_request_class_id
                not in execution_dispatch_class.allowed_execution_request_class_ids
            ):
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template '{template.execution_dispatch_template_id}' uses execution_request_class_id '{template.execution_request_class_id}' outside execution dispatch class '{template.execution_dispatch_class_id}' allowances."
                )
            if not template.required_execution_dispatch_fields:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template '{template.execution_dispatch_template_id}' must declare at least one required_execution_dispatch_field."
                )
            if not template.required_audit_fields:
                raise ExecutionDispatchRegistryError(
                    f"Execution dispatch template '{template.execution_dispatch_template_id}' must declare at least one required_audit_field."
                )
