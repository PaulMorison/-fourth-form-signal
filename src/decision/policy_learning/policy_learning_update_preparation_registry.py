from __future__ import annotations

"""Registry-backed policy-learning update-preparation classes and templates.

Canon ownership:
- Owns governed update-preparation identity and template identity for the
  narrow gate that sits downstream of a non-blocked policy-learning
  update-approval record.
- Does not redefine update-approval judgment, policy mutation,
  rollout or deployment, retraining, monitoring, reopen handling,
  orchestration ownership, or lifecycle meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_UPDATE_APPROVAL_STATUSES = {
    "approval_ready",
    "fallback_template_applied",
}
_VALID_UPDATE_APPROVAL_OUTCOMES = {
    "approved_for_policy_update_preparation",
    "approved_with_restrictions",
    "deferred_pending_additional_governance",
    "blocked_missing_context",
    "rejected_for_policy_update_use",
    "prohibited_overlap_blocked",
}
_VALID_DIMENSION_STRENGTH = {"weak", "moderate", "strong"}
_VALID_UPDATE_PREPARATION_STATUSES = {
    "preparation_ready",
    "fallback_template_applied",
}
_VALID_UPDATE_PREPARATION_OUTCOMES = {
    "prepared_for_policy_mutation_planning",
    "prepared_with_restrictions",
    "deferred_pending_preparation_prerequisites",
}


class PolicyLearningUpdatePreparationRegistryError(ValueError):
    """Base error for policy-learning update-preparation registry failures."""


@dataclass(frozen=True)
class PolicyLearningUpdatePreparationClassDefinition:
    policy_learning_update_preparation_class_id: str
    description: str
    allowed_policy_learning_update_approval_statuses: tuple[str, ...]
    allowed_policy_learning_update_approval_outcomes: tuple[str, ...]
    minimum_dimension_strength: str
    allow_preparation_restrictions: bool
    allow_prerequisite_deferral: bool
    prohibited_update_preparation_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PolicyLearningUpdatePreparationTemplateDefinition:
    policy_learning_update_preparation_template_id: str
    semantic_scope: str
    policy_learning_update_approval_class_id: str
    policy_learning_update_preparation_class_id: str
    required_update_preparation_fields: tuple[str, ...]
    optional_update_preparation_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    policy_learning_update_preparation_status: str
    policy_learning_update_preparation_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PolicyLearningUpdatePreparationRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_approval_class_id: str,
        policy_learning_update_preparation_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdatePreparationTemplateDefinition, bool]:
        """Return the matching update-preparation template and fallback status."""

    def get_policy_learning_update_preparation_class(
        self,
        policy_learning_update_preparation_class_id: str,
    ) -> PolicyLearningUpdatePreparationClassDefinition:
        """Return the named policy-learning update-preparation class."""


class JsonPolicyLearningUpdatePreparationRegistry:
    """Loads policy-learning update-preparation classes and templates."""

    def __init__(
        self,
        *,
        policy_learning_update_preparation_classes_path: Path,
        policy_learning_update_preparation_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._policy_learning_update_preparation_classes = self._load_classes(
            policy_learning_update_preparation_classes_path
        )
        self._policy_learning_update_preparation_templates = self._load_templates(
            policy_learning_update_preparation_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_approval_class_id: str,
        policy_learning_update_preparation_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdatePreparationTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._policy_learning_update_preparation_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_approval_class_id
            == policy_learning_update_approval_class_id
            and template.policy_learning_update_preparation_class_id
            == policy_learning_update_preparation_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.policy_learning_update_preparation_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_preparation_status
                == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._policy_learning_update_preparation_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_approval_class_id
            == policy_learning_update_approval_class_id
            and template.policy_learning_update_preparation_class_id
            == policy_learning_update_preparation_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.policy_learning_update_preparation_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_preparation_status
                == "fallback_template_applied",
            )

        raise PolicyLearningUpdatePreparationRegistryError(
            "No governed policy-learning update-preparation template applies to "
            f"policy_learning_update_preparation_class_id='"
            f"{policy_learning_update_preparation_class_id}' for "
            f"policy_learning_update_approval_class_id='"
            f"{policy_learning_update_approval_class_id}' and route_name='"
            f"{route_name}'."
        )

    def get_policy_learning_update_preparation_class(
        self,
        policy_learning_update_preparation_class_id: str,
    ) -> PolicyLearningUpdatePreparationClassDefinition:
        try:
            return self._policy_learning_update_preparation_classes[
                policy_learning_update_preparation_class_id
            ]
        except KeyError as error:
            raise PolicyLearningUpdatePreparationRegistryError(
                "Policy-learning update-preparation class "
                f"'{policy_learning_update_preparation_class_id}' is not registered."
            ) from error

    def _load_classes(
        self,
        policy_learning_update_preparation_classes_path: Path,
    ) -> dict[str, PolicyLearningUpdatePreparationClassDefinition]:
        content = json.loads(
            policy_learning_update_preparation_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, PolicyLearningUpdatePreparationClassDefinition] = {}
        for class_id, entry in content["policy_learning_update_preparation_classes"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_preparation_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_preparation_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_preparation_class_id"] != class_id:
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation class key "
                    f"'{class_id}' must match "
                    "policy_learning_update_preparation_class_id "
                    f"'{entry['policy_learning_update_preparation_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            if not entry["allowed_policy_learning_update_approval_statuses"]:
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation class "
                    f"'{class_id}' must allow at least one approval status."
                )
            invalid_approval_statuses = sorted(
                set(entry["allowed_policy_learning_update_approval_statuses"])
                - _VALID_UPDATE_APPROVAL_STATUSES
            )
            if invalid_approval_statuses:
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation class "
                    f"'{class_id}' has invalid "
                    "allowed_policy_learning_update_approval_statuses: "
                    + ", ".join(invalid_approval_statuses)
                    + "."
                )
            invalid_approval_outcomes = sorted(
                set(entry["allowed_policy_learning_update_approval_outcomes"])
                - _VALID_UPDATE_APPROVAL_OUTCOMES
            )
            if invalid_approval_outcomes:
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation class "
                    f"'{class_id}' has invalid "
                    "allowed_policy_learning_update_approval_outcomes: "
                    + ", ".join(invalid_approval_outcomes)
                    + "."
                )
            if entry["minimum_dimension_strength"] not in _VALID_DIMENSION_STRENGTH:
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation class "
                    f"'{class_id}' has invalid minimum_dimension_strength "
                    f"'{entry['minimum_dimension_strength']}'."
                )
            class_definitions[class_id] = PolicyLearningUpdatePreparationClassDefinition(
                policy_learning_update_preparation_class_id=entry[
                    "policy_learning_update_preparation_class_id"
                ],
                description=entry["description"],
                allowed_policy_learning_update_approval_statuses=tuple(
                    entry["allowed_policy_learning_update_approval_statuses"]
                ),
                allowed_policy_learning_update_approval_outcomes=tuple(
                    entry["allowed_policy_learning_update_approval_outcomes"]
                ),
                minimum_dimension_strength=entry["minimum_dimension_strength"],
                allow_preparation_restrictions=entry[
                    "allow_preparation_restrictions"
                ],
                allow_prerequisite_deferral=entry[
                    "allow_prerequisite_deferral"
                ],
                prohibited_update_preparation_fields=tuple(
                    entry["prohibited_update_preparation_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_templates(
        self,
        policy_learning_update_preparation_templates_path: Path,
    ) -> tuple[PolicyLearningUpdatePreparationTemplateDefinition, ...]:
        content = json.loads(
            policy_learning_update_preparation_templates_path.read_text(
                encoding="utf-8"
            )
        )
        templates: list[PolicyLearningUpdatePreparationTemplateDefinition] = []
        for template_id, entry in content["policy_learning_update_preparation_templates"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_preparation_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_preparation_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_preparation_template_id"] != template_id:
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation template key "
                    f"'{template_id}' must match "
                    "policy_learning_update_preparation_template_id "
                    f"'{entry['policy_learning_update_preparation_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["policy_learning_update_preparation_status"]
                not in _VALID_UPDATE_PREPARATION_STATUSES
            ):
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation template "
                    f"'{template_id}' has invalid policy_learning_update_preparation_status "
                    f"'{entry['policy_learning_update_preparation_status']}'."
                )
            if (
                entry["policy_learning_update_preparation_outcome"]
                not in _VALID_UPDATE_PREPARATION_OUTCOMES
            ):
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation template "
                    f"'{template_id}' has invalid policy_learning_update_preparation_outcome "
                    f"'{entry['policy_learning_update_preparation_outcome']}'."
                )
            templates.append(
                PolicyLearningUpdatePreparationTemplateDefinition(
                    policy_learning_update_preparation_template_id=entry[
                        "policy_learning_update_preparation_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    policy_learning_update_approval_class_id=entry[
                        "policy_learning_update_approval_class_id"
                    ],
                    policy_learning_update_preparation_class_id=entry[
                        "policy_learning_update_preparation_class_id"
                    ],
                    required_update_preparation_fields=tuple(
                        entry["required_update_preparation_fields"]
                    ),
                    optional_update_preparation_fields=tuple(
                        entry["optional_update_preparation_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    policy_learning_update_preparation_status=entry[
                        "policy_learning_update_preparation_status"
                    ],
                    policy_learning_update_preparation_outcome=entry[
                        "policy_learning_update_preparation_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._policy_learning_update_preparation_templates:
            if (
                template.policy_learning_update_preparation_class_id
                not in self._policy_learning_update_preparation_classes
            ):
                raise PolicyLearningUpdatePreparationRegistryError(
                    "Policy-learning update-preparation template "
                    f"'{template.policy_learning_update_preparation_template_id}' "
                    "references unknown policy_learning_update_preparation_class_id "
                    f"'{template.policy_learning_update_preparation_class_id}'."
                )