from __future__ import annotations

"""Registry-backed policy-learning update-threshold classes and templates.

Canon ownership:
- Owns governed update-threshold identity and template identity for the
  narrow learning-strength gate that sits downstream of admitted
  policy-learning evidence.
- Does not redefine evidence-admission meaning, policy mutation,
  model retraining, deployment, monitoring, reopen handling, or
  orchestration ownership.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_POLICY_LEARNING_EVIDENCE_STATUSES = {
    "admitted_ready",
    "fallback_template_applied",
}
_VALID_POLICY_LEARNING_EVIDENCE_OUTCOMES = {
    "admitted_for_update_consideration",
    "admitted_with_restrictions",
    "deferred_pending_more_evidence",
    "rejected_for_learning_use",
}
_VALID_POLICY_LEARNING_EVIDENCE_SUFFICIENCY = {
    "learning_grade_evidence_sufficient",
    "learning_evidence_restricted",
    "learning_evidence_deferred",
    "learning_evidence_incomplete",
    "learning_evidence_overlap_prohibited",
    "insufficient_for_learning_admission",
}
_VALID_POLICY_LEARNING_EVIDENCE_ATTRIBUTION_READINESS = {
    "attribution_ready_for_learning",
    "attribution_restricted_for_learning",
    "attribution_pending_more_evidence",
    "attribution_not_ready_for_learning",
}
_VALID_DIMENSION_STRENGTH = {"weak", "moderate", "strong"}
_VALID_REPETITION_POSTURES = {
    "single_case_only",
    "limited_repetition",
    "repeated_comparable_cases",
    "exceptional_single_case",
}
_VALID_UPDATE_THRESHOLD_STATUSES = {
    "threshold_met",
    "fallback_template_applied",
}
_VALID_UPDATE_DECISION_OUTCOMES = {
    "accepted",
    "accepted_with_narrowed_scope",
    "deferred_for_continued_monitoring",
}


class PolicyLearningUpdateThresholdRegistryError(ValueError):
    """Base error for policy-learning update-threshold registry failures."""


@dataclass(frozen=True)
class PolicyLearningUpdateThresholdClassDefinition:
    policy_learning_update_threshold_class_id: str
    description: str
    allowed_policy_learning_evidence_statuses: tuple[str, ...]
    allowed_policy_learning_evidence_outcomes: tuple[str, ...]
    minimum_policy_learning_evidence_sufficiency: str
    minimum_policy_learning_evidence_attribution_readiness: str
    minimum_dimension_strength: str
    minimum_repetition_posture: str
    allow_local_scope_narrowing: bool
    allow_monitoring_deferral: bool
    prohibited_update_threshold_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PolicyLearningUpdateThresholdTemplateDefinition:
    policy_learning_update_threshold_template_id: str
    semantic_scope: str
    policy_learning_evidence_class_id: str
    policy_learning_update_threshold_class_id: str
    required_update_threshold_fields: tuple[str, ...]
    optional_update_threshold_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    policy_learning_update_threshold_status: str
    policy_learning_update_decision_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PolicyLearningUpdateThresholdRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_evidence_class_id: str,
        policy_learning_update_threshold_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdateThresholdTemplateDefinition, bool]:
        """Return the matching update-threshold template and fallback status."""

    def get_policy_learning_update_threshold_class(
        self,
        policy_learning_update_threshold_class_id: str,
    ) -> PolicyLearningUpdateThresholdClassDefinition:
        """Return the named policy-learning update-threshold class."""


class JsonPolicyLearningUpdateThresholdRegistry:
    """Loads policy-learning update-threshold classes and templates."""

    def __init__(
        self,
        *,
        policy_learning_update_threshold_classes_path: Path,
        policy_learning_update_threshold_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._policy_learning_update_threshold_classes = self._load_classes(
            policy_learning_update_threshold_classes_path
        )
        self._policy_learning_update_threshold_templates = self._load_templates(
            policy_learning_update_threshold_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_evidence_class_id: str,
        policy_learning_update_threshold_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdateThresholdTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._policy_learning_update_threshold_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_evidence_class_id
            == policy_learning_evidence_class_id
            and template.policy_learning_update_threshold_class_id
            == policy_learning_update_threshold_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.policy_learning_update_threshold_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_threshold_status
                == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._policy_learning_update_threshold_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_evidence_class_id
            == policy_learning_evidence_class_id
            and template.policy_learning_update_threshold_class_id
            == policy_learning_update_threshold_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.policy_learning_update_threshold_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_threshold_status
                == "fallback_template_applied",
            )

        raise PolicyLearningUpdateThresholdRegistryError(
            "No governed policy-learning update-threshold template applies to "
            f"policy_learning_update_threshold_class_id='"
            f"{policy_learning_update_threshold_class_id}' for "
            f"policy_learning_evidence_class_id='"
            f"{policy_learning_evidence_class_id}' and route_name='"
            f"{route_name}'."
        )

    def get_policy_learning_update_threshold_class(
        self,
        policy_learning_update_threshold_class_id: str,
    ) -> PolicyLearningUpdateThresholdClassDefinition:
        try:
            return self._policy_learning_update_threshold_classes[
                policy_learning_update_threshold_class_id
            ]
        except KeyError as error:
            raise PolicyLearningUpdateThresholdRegistryError(
                "Policy-learning update-threshold class "
                f"'{policy_learning_update_threshold_class_id}' is not registered."
            ) from error

    def _load_classes(
        self,
        policy_learning_update_threshold_classes_path: Path,
    ) -> dict[str, PolicyLearningUpdateThresholdClassDefinition]:
        content = json.loads(
            policy_learning_update_threshold_classes_path.read_text(
                encoding="utf-8"
            )
        )
        class_definitions: dict[str, PolicyLearningUpdateThresholdClassDefinition] = {}
        for class_id, entry in content["policy_learning_update_threshold_classes"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_threshold_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_threshold_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_threshold_class_id"] != class_id:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class key "
                    f"'{class_id}' must match "
                    "policy_learning_update_threshold_class_id "
                    f"'{entry['policy_learning_update_threshold_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            if not entry["allowed_policy_learning_evidence_statuses"]:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class "
                    f"'{class_id}' must allow at least one evidence status."
                )
            invalid_evidence_statuses = sorted(
                set(entry["allowed_policy_learning_evidence_statuses"])
                - _VALID_POLICY_LEARNING_EVIDENCE_STATUSES
            )
            if invalid_evidence_statuses:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class "
                    f"'{class_id}' has invalid allowed_policy_learning_evidence_statuses: "
                    + ", ".join(invalid_evidence_statuses)
                    + "."
                )
            invalid_evidence_outcomes = sorted(
                set(entry["allowed_policy_learning_evidence_outcomes"])
                - _VALID_POLICY_LEARNING_EVIDENCE_OUTCOMES
            )
            if invalid_evidence_outcomes:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class "
                    f"'{class_id}' has invalid allowed_policy_learning_evidence_outcomes: "
                    + ", ".join(invalid_evidence_outcomes)
                    + "."
                )
            if (
                entry["minimum_policy_learning_evidence_sufficiency"]
                not in _VALID_POLICY_LEARNING_EVIDENCE_SUFFICIENCY
            ):
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class "
                    f"'{class_id}' has invalid minimum_policy_learning_evidence_sufficiency "
                    f"'{entry['minimum_policy_learning_evidence_sufficiency']}'."
                )
            if (
                entry["minimum_policy_learning_evidence_attribution_readiness"]
                not in _VALID_POLICY_LEARNING_EVIDENCE_ATTRIBUTION_READINESS
            ):
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class "
                    f"'{class_id}' has invalid "
                    "minimum_policy_learning_evidence_attribution_readiness "
                    f"'{entry['minimum_policy_learning_evidence_attribution_readiness']}'."
                )
            if entry["minimum_dimension_strength"] not in _VALID_DIMENSION_STRENGTH:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class "
                    f"'{class_id}' has invalid minimum_dimension_strength "
                    f"'{entry['minimum_dimension_strength']}'."
                )
            if entry["minimum_repetition_posture"] not in _VALID_REPETITION_POSTURES:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold class "
                    f"'{class_id}' has invalid minimum_repetition_posture "
                    f"'{entry['minimum_repetition_posture']}'."
                )
            class_definitions[class_id] = PolicyLearningUpdateThresholdClassDefinition(
                policy_learning_update_threshold_class_id=entry[
                    "policy_learning_update_threshold_class_id"
                ],
                description=entry["description"],
                allowed_policy_learning_evidence_statuses=tuple(
                    entry["allowed_policy_learning_evidence_statuses"]
                ),
                allowed_policy_learning_evidence_outcomes=tuple(
                    entry["allowed_policy_learning_evidence_outcomes"]
                ),
                minimum_policy_learning_evidence_sufficiency=entry[
                    "minimum_policy_learning_evidence_sufficiency"
                ],
                minimum_policy_learning_evidence_attribution_readiness=entry[
                    "minimum_policy_learning_evidence_attribution_readiness"
                ],
                minimum_dimension_strength=entry["minimum_dimension_strength"],
                minimum_repetition_posture=entry["minimum_repetition_posture"],
                allow_local_scope_narrowing=entry["allow_local_scope_narrowing"],
                allow_monitoring_deferral=entry["allow_monitoring_deferral"],
                prohibited_update_threshold_fields=tuple(
                    entry["prohibited_update_threshold_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_templates(
        self,
        policy_learning_update_threshold_templates_path: Path,
    ) -> tuple[PolicyLearningUpdateThresholdTemplateDefinition, ...]:
        content = json.loads(
            policy_learning_update_threshold_templates_path.read_text(
                encoding="utf-8"
            )
        )
        templates: list[PolicyLearningUpdateThresholdTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content[
            "policy_learning_update_threshold_templates"
        ].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_threshold_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_threshold_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_threshold_template_id"] != template_id:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold template key "
                    f"'{template_id}' must match "
                    "policy_learning_update_threshold_template_id "
                    f"'{entry['policy_learning_update_threshold_template_id']}'."
                )
            if template_id in template_ids:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Duplicate policy_learning_update_threshold_template_id "
                    f"'{template_id}' found in update-threshold template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["policy_learning_update_threshold_status"]
                not in _VALID_UPDATE_THRESHOLD_STATUSES
            ):
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold template "
                    f"'{template_id}' has invalid policy_learning_update_threshold_status "
                    f"'{entry['policy_learning_update_threshold_status']}'."
                )
            if (
                entry["policy_learning_update_decision_outcome"]
                not in _VALID_UPDATE_DECISION_OUTCOMES
            ):
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold template "
                    f"'{template_id}' has invalid policy_learning_update_decision_outcome "
                    f"'{entry['policy_learning_update_decision_outcome']}'."
                )
            templates.append(
                PolicyLearningUpdateThresholdTemplateDefinition(
                    policy_learning_update_threshold_template_id=entry[
                        "policy_learning_update_threshold_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    policy_learning_evidence_class_id=entry[
                        "policy_learning_evidence_class_id"
                    ],
                    policy_learning_update_threshold_class_id=entry[
                        "policy_learning_update_threshold_class_id"
                    ],
                    required_update_threshold_fields=tuple(
                        entry["required_update_threshold_fields"]
                    ),
                    optional_update_threshold_fields=tuple(
                        entry["optional_update_threshold_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    policy_learning_update_threshold_status=entry[
                        "policy_learning_update_threshold_status"
                    ],
                    policy_learning_update_decision_outcome=entry[
                        "policy_learning_update_decision_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._policy_learning_update_threshold_templates:
            class_definition = self._policy_learning_update_threshold_classes.get(
                template.policy_learning_update_threshold_class_id
            )
            if class_definition is None:
                raise PolicyLearningUpdateThresholdRegistryError(
                    "Policy-learning update-threshold template "
                    f"'{template.policy_learning_update_threshold_template_id}' references "
                    "unknown policy_learning_update_threshold_class_id '"
                    f"{template.policy_learning_update_threshold_class_id}'."
                )
