from __future__ import annotations

"""Registry-backed policy-learning update-mutation-planning classes and templates.

Canon ownership:
- Owns governed update-mutation-planning identity and template identity for the
    narrow gate that sits downstream of a non-blocked policy-learning
    update-preparation record.
- Does not redefine update-preparation judgment, policy mutation execution,
    rollout or deployment execution, retraining execution, monitoring, reopen
    handling, orchestration ownership, or lifecycle meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_UPDATE_PREPARATION_STATUSES = {
    "preparation_ready",
    "fallback_template_applied",
}
_VALID_UPDATE_PREPARATION_OUTCOMES = {
    "prepared_for_policy_mutation_planning",
    "prepared_with_restrictions",
    "deferred_pending_preparation_prerequisites",
    "blocked_missing_context",
    "rejected_for_preparation_use",
    "prohibited_overlap_blocked",
}
_VALID_DIMENSION_STRENGTH = {"weak", "moderate", "strong"}
_VALID_UPDATE_MUTATION_PLANNING_STATUSES = {
    "mutation_planning_ready",
    "fallback_template_applied",
}
_VALID_UPDATE_MUTATION_PLANNING_OUTCOMES = {
    "ready_for_policy_mutation_planning",
    "ready_for_policy_mutation_planning_with_restrictions",
    "deferred_pending_mutation_planning_prerequisites",
}


class PolicyLearningUpdateMutationPlanningRegistryError(ValueError):
    """Base error for policy-learning update-mutation-planning registry failures."""


@dataclass(frozen=True)
class PolicyLearningUpdateMutationPlanningClassDefinition:
    policy_learning_update_mutation_planning_class_id: str
    description: str
    allowed_policy_learning_update_preparation_statuses: tuple[str, ...]
    allowed_policy_learning_update_preparation_outcomes: tuple[str, ...]
    minimum_dimension_strength: str
    allow_mutation_planning_restrictions: bool
    allow_mutation_planning_prerequisite_deferral: bool
    prohibited_update_mutation_planning_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PolicyLearningUpdateMutationPlanningTemplateDefinition:
    policy_learning_update_mutation_planning_template_id: str
    semantic_scope: str
    policy_learning_update_preparation_class_id: str
    policy_learning_update_mutation_planning_class_id: str
    required_update_mutation_planning_fields: tuple[str, ...]
    optional_update_mutation_planning_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    policy_learning_update_mutation_planning_status: str
    policy_learning_update_mutation_planning_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PolicyLearningUpdateMutationPlanningRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_preparation_class_id: str,
        policy_learning_update_mutation_planning_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdateMutationPlanningTemplateDefinition, bool]:
        """Return the matching update-mutation-planning template and fallback status."""

    def get_policy_learning_update_mutation_planning_class(
        self,
        policy_learning_update_mutation_planning_class_id: str,
    ) -> PolicyLearningUpdateMutationPlanningClassDefinition:
        """Return the named policy-learning update-mutation-planning class."""


class JsonPolicyLearningUpdateMutationPlanningRegistry:
    """Loads policy-learning update-mutation-planning classes and templates."""

    def __init__(
        self,
        *,
        policy_learning_update_mutation_planning_classes_path: Path,
        policy_learning_update_mutation_planning_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._policy_learning_update_mutation_planning_classes = self._load_classes(
            policy_learning_update_mutation_planning_classes_path
        )
        self._policy_learning_update_mutation_planning_templates = self._load_templates(
            policy_learning_update_mutation_planning_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_preparation_class_id: str,
        policy_learning_update_mutation_planning_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdateMutationPlanningTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._policy_learning_update_mutation_planning_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_preparation_class_id
            == policy_learning_update_preparation_class_id
            and template.policy_learning_update_mutation_planning_class_id
            == policy_learning_update_mutation_planning_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.policy_learning_update_mutation_planning_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_mutation_planning_status
                == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._policy_learning_update_mutation_planning_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_preparation_class_id
            == policy_learning_update_preparation_class_id
            and template.policy_learning_update_mutation_planning_class_id
            == policy_learning_update_mutation_planning_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.policy_learning_update_mutation_planning_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_mutation_planning_status
                == "fallback_template_applied",
            )

        raise PolicyLearningUpdateMutationPlanningRegistryError(
            "No governed policy-learning update-mutation-planning template applies to "
            f"policy_learning_update_mutation_planning_class_id='"
            f"{policy_learning_update_mutation_planning_class_id}' for "
            f"policy_learning_update_preparation_class_id='"
            f"{policy_learning_update_preparation_class_id}' and route_name='"
            f"{route_name}'."
        )

    def get_policy_learning_update_mutation_planning_class(
        self,
        policy_learning_update_mutation_planning_class_id: str,
    ) -> PolicyLearningUpdateMutationPlanningClassDefinition:
        try:
            return self._policy_learning_update_mutation_planning_classes[
                policy_learning_update_mutation_planning_class_id
            ]
        except KeyError as error:
            raise PolicyLearningUpdateMutationPlanningRegistryError(
                "Policy-learning update-mutation-planning class "
                f"'{policy_learning_update_mutation_planning_class_id}' is not registered."
            ) from error

    def _load_classes(
        self,
        policy_learning_update_mutation_planning_classes_path: Path,
    ) -> dict[str, PolicyLearningUpdateMutationPlanningClassDefinition]:
        content = json.loads(
            policy_learning_update_mutation_planning_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, PolicyLearningUpdateMutationPlanningClassDefinition] = {}
        for class_id, entry in content["policy_learning_update_mutation_planning_classes"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_mutation_planning_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_mutation_planning_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_mutation_planning_class_id"] != class_id:
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning class key "
                    f"'{class_id}' must match "
                    "policy_learning_update_mutation_planning_class_id "
                    f"'{entry['policy_learning_update_mutation_planning_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            if not entry["allowed_policy_learning_update_preparation_statuses"]:
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning class "
                    f"'{class_id}' must allow at least one preparation status."
                )
            invalid_preparation_statuses = sorted(
                set(entry["allowed_policy_learning_update_preparation_statuses"])
                - _VALID_UPDATE_PREPARATION_STATUSES
            )
            if invalid_preparation_statuses:
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning class "
                    f"'{class_id}' has invalid "
                    "allowed_policy_learning_update_preparation_statuses: "
                    + ", ".join(invalid_preparation_statuses)
                    + "."
                )
            invalid_preparation_outcomes = sorted(
                set(entry["allowed_policy_learning_update_preparation_outcomes"])
                - _VALID_UPDATE_PREPARATION_OUTCOMES
            )
            if invalid_preparation_outcomes:
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning class "
                    f"'{class_id}' has invalid "
                    "allowed_policy_learning_update_preparation_outcomes: "
                    + ", ".join(invalid_preparation_outcomes)
                    + "."
                )
            if entry["minimum_dimension_strength"] not in _VALID_DIMENSION_STRENGTH:
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning class "
                    f"'{class_id}' has invalid minimum_dimension_strength "
                    f"'{entry['minimum_dimension_strength']}'."
                )
            class_definitions[class_id] = PolicyLearningUpdateMutationPlanningClassDefinition(
                policy_learning_update_mutation_planning_class_id=entry[
                    "policy_learning_update_mutation_planning_class_id"
                ],
                description=entry["description"],
                allowed_policy_learning_update_preparation_statuses=tuple(
                    entry["allowed_policy_learning_update_preparation_statuses"]
                ),
                allowed_policy_learning_update_preparation_outcomes=tuple(
                    entry["allowed_policy_learning_update_preparation_outcomes"]
                ),
                minimum_dimension_strength=entry["minimum_dimension_strength"],
                allow_mutation_planning_restrictions=entry[
                    "allow_mutation_planning_restrictions"
                ],
                allow_mutation_planning_prerequisite_deferral=entry[
                    "allow_mutation_planning_prerequisite_deferral"
                ],
                prohibited_update_mutation_planning_fields=tuple(
                    entry["prohibited_update_mutation_planning_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_templates(
        self,
        policy_learning_update_mutation_planning_templates_path: Path,
    ) -> tuple[PolicyLearningUpdateMutationPlanningTemplateDefinition, ...]:
        content = json.loads(
            policy_learning_update_mutation_planning_templates_path.read_text(
                encoding="utf-8"
            )
        )
        templates: list[PolicyLearningUpdateMutationPlanningTemplateDefinition] = []
        for template_id, entry in content["policy_learning_update_mutation_planning_templates"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_mutation_planning_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_mutation_planning_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_mutation_planning_template_id"] != template_id:
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning template key "
                    f"'{template_id}' must match "
                    "policy_learning_update_mutation_planning_template_id "
                    f"'{entry['policy_learning_update_mutation_planning_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["policy_learning_update_mutation_planning_status"]
                not in _VALID_UPDATE_MUTATION_PLANNING_STATUSES
            ):
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning template "
                    f"'{template_id}' has invalid policy_learning_update_mutation_planning_status "
                    f"'{entry['policy_learning_update_mutation_planning_status']}'."
                )
            if (
                entry["policy_learning_update_mutation_planning_outcome"]
                not in _VALID_UPDATE_MUTATION_PLANNING_OUTCOMES
            ):
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning template "
                    f"'{template_id}' has invalid policy_learning_update_mutation_planning_outcome "
                    f"'{entry['policy_learning_update_mutation_planning_outcome']}'."
                )
            templates.append(
                PolicyLearningUpdateMutationPlanningTemplateDefinition(
                    policy_learning_update_mutation_planning_template_id=entry[
                        "policy_learning_update_mutation_planning_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    policy_learning_update_preparation_class_id=entry[
                        "policy_learning_update_preparation_class_id"
                    ],
                    policy_learning_update_mutation_planning_class_id=entry[
                        "policy_learning_update_mutation_planning_class_id"
                    ],
                    required_update_mutation_planning_fields=tuple(
                        entry["required_update_mutation_planning_fields"]
                    ),
                    optional_update_mutation_planning_fields=tuple(
                        entry["optional_update_mutation_planning_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    policy_learning_update_mutation_planning_status=entry[
                        "policy_learning_update_mutation_planning_status"
                    ],
                    policy_learning_update_mutation_planning_outcome=entry[
                        "policy_learning_update_mutation_planning_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._policy_learning_update_mutation_planning_templates:
            if (
                template.policy_learning_update_mutation_planning_class_id
                not in self._policy_learning_update_mutation_planning_classes
            ):
                raise PolicyLearningUpdateMutationPlanningRegistryError(
                    "Policy-learning update-mutation-planning template "
                    f"'{template.policy_learning_update_mutation_planning_template_id}' "
                    "references unknown policy_learning_update_mutation_planning_class_id "
                    f"'{template.policy_learning_update_mutation_planning_class_id}'."
                )