from __future__ import annotations

"""Registry-backed policy-learning update-mutation-execution classes and templates.

Canon ownership:
- Owns governed update-mutation-execution identity and template identity for the
  narrow gate that sits downstream of a non-blocked policy-learning
  update-mutation-planning record.
- Does not redefine mutation-planning judgment, rollout or deployment
  execution, retraining execution, model update execution, monitoring,
  reopen handling, orchestration ownership, or lifecycle meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_UPDATE_MUTATION_PLANNING_STATUSES = {
    "mutation_planning_ready",
    "fallback_template_applied",
}
_VALID_UPDATE_MUTATION_PLANNING_OUTCOMES = {
    "ready_for_policy_mutation_planning",
    "ready_for_policy_mutation_planning_with_restrictions",
    "deferred_pending_mutation_planning_prerequisites",
    "blocked_missing_context",
    "rejected_for_mutation_planning_use",
    "prohibited_overlap_blocked",
}
_VALID_DIMENSION_STRENGTH = {"weak", "moderate", "strong"}
_VALID_UPDATE_MUTATION_EXECUTION_STATUSES = {
    "mutation_execution_ready",
    "fallback_template_applied",
}
_VALID_UPDATE_MUTATION_EXECUTION_OUTCOMES = {
    "ready_for_policy_mutation_execution",
    "ready_for_policy_mutation_execution_with_restrictions",
    "deferred_pending_mutation_execution_prerequisites",
}


class PolicyLearningUpdateMutationExecutionRegistryError(ValueError):
    """Base error for policy-learning update-mutation-execution registry failures."""


@dataclass(frozen=True)
class PolicyLearningUpdateMutationExecutionClassDefinition:
    policy_learning_update_mutation_execution_class_id: str
    description: str
    allowed_policy_learning_update_mutation_planning_statuses: tuple[str, ...]
    allowed_policy_learning_update_mutation_planning_outcomes: tuple[str, ...]
    minimum_dimension_strength: str
    allow_mutation_execution_restrictions: bool
    allow_mutation_execution_prerequisite_deferral: bool
    prohibited_update_mutation_execution_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PolicyLearningUpdateMutationExecutionTemplateDefinition:
    policy_learning_update_mutation_execution_template_id: str
    semantic_scope: str
    policy_learning_update_mutation_planning_class_id: str
    policy_learning_update_mutation_execution_class_id: str
    required_update_mutation_execution_fields: tuple[str, ...]
    optional_update_mutation_execution_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    policy_learning_update_mutation_execution_status: str
    policy_learning_update_mutation_execution_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PolicyLearningUpdateMutationExecutionRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_mutation_planning_class_id: str,
        policy_learning_update_mutation_execution_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdateMutationExecutionTemplateDefinition, bool]:
        """Return the matching update-mutation-execution template and fallback status."""

    def get_policy_learning_update_mutation_execution_class(
        self,
        policy_learning_update_mutation_execution_class_id: str,
    ) -> PolicyLearningUpdateMutationExecutionClassDefinition:
        """Return the named policy-learning update-mutation-execution class."""


class JsonPolicyLearningUpdateMutationExecutionRegistry:
    """Loads policy-learning update-mutation-execution classes and templates."""

    def __init__(
        self,
        *,
        policy_learning_update_mutation_execution_classes_path: Path,
        policy_learning_update_mutation_execution_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._policy_learning_update_mutation_execution_classes = self._load_classes(
            policy_learning_update_mutation_execution_classes_path
        )
        self._policy_learning_update_mutation_execution_templates = self._load_templates(
            policy_learning_update_mutation_execution_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_mutation_planning_class_id: str,
        policy_learning_update_mutation_execution_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdateMutationExecutionTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._policy_learning_update_mutation_execution_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_mutation_planning_class_id
            == policy_learning_update_mutation_planning_class_id
            and template.policy_learning_update_mutation_execution_class_id
            == policy_learning_update_mutation_execution_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.policy_learning_update_mutation_execution_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_mutation_execution_status
                == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._policy_learning_update_mutation_execution_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_mutation_planning_class_id
            == policy_learning_update_mutation_planning_class_id
            and template.policy_learning_update_mutation_execution_class_id
            == policy_learning_update_mutation_execution_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.policy_learning_update_mutation_execution_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_mutation_execution_status
                == "fallback_template_applied",
            )

        raise PolicyLearningUpdateMutationExecutionRegistryError(
            "No governed policy-learning update-mutation-execution template applies to "
            f"policy_learning_update_mutation_execution_class_id='"
            f"{policy_learning_update_mutation_execution_class_id}' for "
            f"policy_learning_update_mutation_planning_class_id='"
            f"{policy_learning_update_mutation_planning_class_id}' and route_name='"
            f"{route_name}'."
        )

    def get_policy_learning_update_mutation_execution_class(
        self,
        policy_learning_update_mutation_execution_class_id: str,
    ) -> PolicyLearningUpdateMutationExecutionClassDefinition:
        try:
            return self._policy_learning_update_mutation_execution_classes[
                policy_learning_update_mutation_execution_class_id
            ]
        except KeyError as error:
            raise PolicyLearningUpdateMutationExecutionRegistryError(
                "Policy-learning update-mutation-execution class "
                f"'{policy_learning_update_mutation_execution_class_id}' is not registered."
            ) from error

    def _load_classes(
        self,
        policy_learning_update_mutation_execution_classes_path: Path,
    ) -> dict[str, PolicyLearningUpdateMutationExecutionClassDefinition]:
        content = json.loads(
            policy_learning_update_mutation_execution_classes_path.read_text(
                encoding="utf-8"
            )
        )
        class_definitions: dict[str, PolicyLearningUpdateMutationExecutionClassDefinition] = {}
        for class_id, entry in content["policy_learning_update_mutation_execution_classes"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_mutation_execution_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_mutation_execution_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_mutation_execution_class_id"] != class_id:
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution class key "
                    f"'{class_id}' must match "
                    "policy_learning_update_mutation_execution_class_id "
                    f"'{entry['policy_learning_update_mutation_execution_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_planning_statuses = sorted(
                set(entry["allowed_policy_learning_update_mutation_planning_statuses"])
                - _VALID_UPDATE_MUTATION_PLANNING_STATUSES
            )
            if invalid_planning_statuses:
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution class "
                    f"'{class_id}' has invalid "
                    "allowed_policy_learning_update_mutation_planning_statuses: "
                    + ", ".join(invalid_planning_statuses)
                    + "."
                )
            invalid_planning_outcomes = sorted(
                set(entry["allowed_policy_learning_update_mutation_planning_outcomes"])
                - _VALID_UPDATE_MUTATION_PLANNING_OUTCOMES
            )
            if invalid_planning_outcomes:
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution class "
                    f"'{class_id}' has invalid "
                    "allowed_policy_learning_update_mutation_planning_outcomes: "
                    + ", ".join(invalid_planning_outcomes)
                    + "."
                )
            if entry["minimum_dimension_strength"] not in _VALID_DIMENSION_STRENGTH:
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution class "
                    f"'{class_id}' has invalid minimum_dimension_strength "
                    f"'{entry['minimum_dimension_strength']}'."
                )
            class_definitions[class_id] = PolicyLearningUpdateMutationExecutionClassDefinition(
                policy_learning_update_mutation_execution_class_id=entry[
                    "policy_learning_update_mutation_execution_class_id"
                ],
                description=entry["description"],
                allowed_policy_learning_update_mutation_planning_statuses=tuple(
                    entry["allowed_policy_learning_update_mutation_planning_statuses"]
                ),
                allowed_policy_learning_update_mutation_planning_outcomes=tuple(
                    entry["allowed_policy_learning_update_mutation_planning_outcomes"]
                ),
                minimum_dimension_strength=entry["minimum_dimension_strength"],
                allow_mutation_execution_restrictions=entry[
                    "allow_mutation_execution_restrictions"
                ],
                allow_mutation_execution_prerequisite_deferral=entry[
                    "allow_mutation_execution_prerequisite_deferral"
                ],
                prohibited_update_mutation_execution_fields=tuple(
                    entry["prohibited_update_mutation_execution_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_templates(
        self,
        policy_learning_update_mutation_execution_templates_path: Path,
    ) -> tuple[PolicyLearningUpdateMutationExecutionTemplateDefinition, ...]:
        content = json.loads(
            policy_learning_update_mutation_execution_templates_path.read_text(
                encoding="utf-8"
            )
        )
        templates: list[PolicyLearningUpdateMutationExecutionTemplateDefinition] = []
        for template_id, entry in content[
            "policy_learning_update_mutation_execution_templates"
        ].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_mutation_execution_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_mutation_execution_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_mutation_execution_template_id"] != template_id:
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution template key "
                    f"'{template_id}' must match "
                    "policy_learning_update_mutation_execution_template_id "
                    f"'{entry['policy_learning_update_mutation_execution_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["policy_learning_update_mutation_execution_status"]
                not in _VALID_UPDATE_MUTATION_EXECUTION_STATUSES
            ):
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution template "
                    f"'{template_id}' has invalid status '"
                    f"{entry['policy_learning_update_mutation_execution_status']}'."
                )
            if (
                entry["policy_learning_update_mutation_execution_outcome"]
                not in _VALID_UPDATE_MUTATION_EXECUTION_OUTCOMES
            ):
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution template "
                    f"'{template_id}' has invalid outcome '"
                    f"{entry['policy_learning_update_mutation_execution_outcome']}'."
                )
            templates.append(
                PolicyLearningUpdateMutationExecutionTemplateDefinition(
                    policy_learning_update_mutation_execution_template_id=entry[
                        "policy_learning_update_mutation_execution_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    policy_learning_update_mutation_planning_class_id=entry[
                        "policy_learning_update_mutation_planning_class_id"
                    ],
                    policy_learning_update_mutation_execution_class_id=entry[
                        "policy_learning_update_mutation_execution_class_id"
                    ],
                    required_update_mutation_execution_fields=tuple(
                        entry["required_update_mutation_execution_fields"]
                    ),
                    optional_update_mutation_execution_fields=tuple(
                        entry["optional_update_mutation_execution_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    policy_learning_update_mutation_execution_status=entry[
                        "policy_learning_update_mutation_execution_status"
                    ],
                    policy_learning_update_mutation_execution_outcome=entry[
                        "policy_learning_update_mutation_execution_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._policy_learning_update_mutation_execution_templates:
            if (
                template.policy_learning_update_mutation_execution_class_id
                not in self._policy_learning_update_mutation_execution_classes
            ):
                raise PolicyLearningUpdateMutationExecutionRegistryError(
                    "Policy-learning update-mutation-execution template '"
                    f"{template.policy_learning_update_mutation_execution_template_id}' "
                    "references unknown mutation-execution class '"
                    f"{template.policy_learning_update_mutation_execution_class_id}'."
                )
