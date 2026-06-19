from __future__ import annotations

"""Registry-backed execution-outcome classes and capture templates.

Canon ownership:
- Owns governed execution-outcome identity and template identity for bounded
  outcome-capture records emitted after legitimate execution-dispatch
  boundaries.
- Does not perform execution, redefine execution-dispatch meaning, or absorb
  broker, venue, post-mortem, or policy-learning admission semantics.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_REALIZED_RESULT_CLASSES = {
    "favorable",
    "negative",
    "mixed",
    "incomplete",
    "deferred",
    "exception_bearing",
}
_VALID_EXECUTION_OUTCOME_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}
_VALID_FEEDBACK_CAPTURE_READINESS = {
    "feedback_capture_ready_for_post_mortem",
    "feedback_capture_deferred",
    "feedback_capture_incomplete",
}


class ExecutionOutcomeRegistryError(ValueError):
    """Base error for execution-outcome registry failures."""


@dataclass(frozen=True)
class ExecutionOutcomeClassDefinition:
    execution_outcome_class_id: str
    description: str
    realized_result_class: str
    allowed_execution_dispatch_class_ids: tuple[str, ...]
    prohibited_observation_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ExecutionOutcomeTemplateDefinition:
    execution_outcome_template_id: str
    semantic_scope: str
    execution_dispatch_class_id: str
    execution_outcome_class_id: str
    required_execution_outcome_fields: tuple[str, ...]
    optional_execution_outcome_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    execution_outcome_status: str
    feedback_capture_readiness: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class ExecutionOutcomeRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        execution_dispatch_class_id: str,
        execution_outcome_class_id: str,
        route_name: str | None,
    ) -> tuple[ExecutionOutcomeTemplateDefinition, bool]:
        """Return the matching execution-outcome template and fallback status."""

    def get_execution_outcome_class(
        self,
        execution_outcome_class_id: str,
    ) -> ExecutionOutcomeClassDefinition:
        """Return the named execution-outcome class."""


class JsonExecutionOutcomeRegistry:
    """Loads execution-outcome classes and templates from checked-in registries."""

    def __init__(
        self,
        *,
        execution_outcome_classes_path: Path,
        execution_outcome_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._execution_outcome_classes = self._load_execution_outcome_classes(
            execution_outcome_classes_path
        )
        self._execution_outcome_templates = self._load_execution_outcome_templates(
            execution_outcome_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        execution_dispatch_class_id: str,
        execution_outcome_class_id: str,
        route_name: str | None,
    ) -> tuple[ExecutionOutcomeTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._execution_outcome_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.execution_dispatch_class_id == execution_dispatch_class_id
            and template.execution_outcome_class_id == execution_outcome_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.execution_outcome_template_id,
            )[0]
            return template, template.execution_outcome_status == "fallback_template_applied"

        generic_matches = tuple(
            template
            for template in self._execution_outcome_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.execution_dispatch_class_id == execution_dispatch_class_id
            and template.execution_outcome_class_id == execution_outcome_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.execution_outcome_template_id,
            )[0]
            return template, template.execution_outcome_status == "fallback_template_applied"

        raise ExecutionOutcomeRegistryError(
            "No governed execution-outcome template applies to execution_outcome_class_id="
            f"'{execution_outcome_class_id}' for execution_dispatch_class_id='{execution_dispatch_class_id}' "
            f"and route_name='{route_name}'."
        )

    def get_execution_outcome_class(
        self,
        execution_outcome_class_id: str,
    ) -> ExecutionOutcomeClassDefinition:
        try:
            return self._execution_outcome_classes[execution_outcome_class_id]
        except KeyError as error:
            raise ExecutionOutcomeRegistryError(
                f"Execution outcome class '{execution_outcome_class_id}' is not registered."
            ) from error

    def _load_execution_outcome_classes(
        self,
        execution_outcome_classes_path: Path,
    ) -> dict[str, ExecutionOutcomeClassDefinition]:
        content = json.loads(execution_outcome_classes_path.read_text(encoding="utf-8"))
        execution_outcome_classes: dict[str, ExecutionOutcomeClassDefinition] = {}
        for class_id, entry in content["execution_outcome_classes"].items():
            self._contract_validator.validate_or_raise(
                "execution_outcome_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="execution_outcome_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["execution_outcome_class_id"] != class_id:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome class key '{class_id}' must match execution_outcome_class_id '{entry['execution_outcome_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["realized_result_class"] not in _VALID_REALIZED_RESULT_CLASSES:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome class '{class_id}' has invalid realized_result_class '{entry['realized_result_class']}'."
                )
            execution_outcome_classes[class_id] = ExecutionOutcomeClassDefinition(
                execution_outcome_class_id=entry["execution_outcome_class_id"],
                description=entry["description"],
                realized_result_class=entry["realized_result_class"],
                allowed_execution_dispatch_class_ids=tuple(
                    entry["allowed_execution_dispatch_class_ids"]
                ),
                prohibited_observation_fields=tuple(
                    entry["prohibited_observation_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return execution_outcome_classes

    def _load_execution_outcome_templates(
        self,
        execution_outcome_templates_path: Path,
    ) -> tuple[ExecutionOutcomeTemplateDefinition, ...]:
        content = json.loads(execution_outcome_templates_path.read_text(encoding="utf-8"))
        execution_outcome_templates: list[ExecutionOutcomeTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["execution_outcome_templates"].items():
            self._contract_validator.validate_or_raise(
                "execution_outcome_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="execution_outcome_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["execution_outcome_template_id"] != template_id:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template key '{template_id}' must match execution_outcome_template_id '{entry['execution_outcome_template_id']}'."
                )
            if template_id in template_ids:
                raise ExecutionOutcomeRegistryError(
                    f"Duplicate execution_outcome_template_id '{template_id}' found in execution outcome template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["execution_outcome_status"] not in _VALID_EXECUTION_OUTCOME_STATUSES:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template '{template_id}' has invalid execution_outcome_status '{entry['execution_outcome_status']}'."
                )
            if entry["feedback_capture_readiness"] not in _VALID_FEEDBACK_CAPTURE_READINESS:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template '{template_id}' has invalid feedback_capture_readiness '{entry['feedback_capture_readiness']}'."
                )
            execution_outcome_templates.append(
                ExecutionOutcomeTemplateDefinition(
                    execution_outcome_template_id=entry["execution_outcome_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    execution_dispatch_class_id=entry["execution_dispatch_class_id"],
                    execution_outcome_class_id=entry["execution_outcome_class_id"],
                    required_execution_outcome_fields=tuple(
                        entry["required_execution_outcome_fields"]
                    ),
                    optional_execution_outcome_fields=tuple(
                        entry["optional_execution_outcome_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    execution_outcome_status=entry["execution_outcome_status"],
                    feedback_capture_readiness=entry["feedback_capture_readiness"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(execution_outcome_templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._execution_outcome_templates:
            execution_outcome_class = self._execution_outcome_classes.get(
                template.execution_outcome_class_id
            )
            if execution_outcome_class is None:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template '{template.execution_outcome_template_id}' references unknown execution_outcome_class_id '{template.execution_outcome_class_id}'."
                )
            if execution_outcome_class.status != "active":
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template '{template.execution_outcome_template_id}' references inactive execution outcome class '{template.execution_outcome_class_id}'."
                )
            if (
                template.execution_dispatch_class_id
                not in execution_outcome_class.allowed_execution_dispatch_class_ids
            ):
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template '{template.execution_outcome_template_id}' uses execution_dispatch_class_id '{template.execution_dispatch_class_id}' outside execution outcome class '{template.execution_outcome_class_id}' allowances."
                )
            if not template.required_execution_outcome_fields:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template '{template.execution_outcome_template_id}' must declare at least one required_execution_outcome_field."
                )
            if not template.required_audit_fields:
                raise ExecutionOutcomeRegistryError(
                    f"Execution outcome template '{template.execution_outcome_template_id}' must declare at least one required_audit_field."
                )