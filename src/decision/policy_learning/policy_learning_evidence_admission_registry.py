from __future__ import annotations

"""Registry-backed policy-learning evidence-admission classes and templates.

Canon ownership:
- Owns governed evidence-admission identity and template identity for the
  narrow learning gate that sits downstream of legitimate post-mortem
  judgments.
- Does not redefine post-mortem attribution meaning, reopen handling,
  monitoring, model mutation, or policy-update execution semantics.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_POST_MORTEM_JUDGMENT_CLASS_IDS = {
    "correct_recommendation_correct_execution",
    "correct_recommendation_weak_execution",
    "correct_recommendation_environment_changed",
    "weak_recommendation_good_execution",
    "weak_recommendation_weak_causal_logic",
    "weak_recommendation_poor_local_state_capture",
    "weak_recommendation_simulation_miss",
    "weak_recommendation_constraint_miss",
    "override_improved_outcome",
    "override_worsened_outcome",
    "insufficient_evidence_for_confident_judgment",
}
_VALID_POST_MORTEM_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}
_VALID_EVIDENCE_QUALITIES = {
    "strong_reconstructible_evidence",
    "mixed_evidence_requires_caution",
    "immature_observation_horizon",
    "insufficient_reconstructible_evidence",
}
_VALID_CONFIDENCE_POSTURES = {
    "confident_for_attribution",
    "cautious_for_review_only",
    "insufficient_for_confident_judgment",
}
_VALID_ADMISSION_STATUSES = {
    "admitted_ready",
    "fallback_template_applied",
}
_VALID_ADMISSION_OUTCOMES = {
    "admitted_for_update_consideration",
    "admitted_with_restrictions",
    "deferred_pending_more_evidence",
}


class PolicyLearningEvidenceAdmissionRegistryError(ValueError):
    """Base error for policy-learning evidence-admission registry failures."""


@dataclass(frozen=True)
class PolicyLearningEvidenceAdmissionClassDefinition:
    policy_learning_evidence_class_id: str
    description: str
    allowed_post_mortem_judgment_class_ids: tuple[str, ...]
    allowed_post_mortem_statuses: tuple[str, ...]
    minimum_evidence_quality: str
    minimum_confidence_posture: str
    prohibited_evidence_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PolicyLearningEvidenceAdmissionTemplateDefinition:
    policy_learning_evidence_template_id: str
    semantic_scope: str
    post_mortem_judgment_class_id: str
    policy_learning_evidence_class_id: str
    required_evidence_fields: tuple[str, ...]
    optional_evidence_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    policy_learning_evidence_admission_status: str
    policy_learning_evidence_admission_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PolicyLearningEvidenceAdmissionRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        post_mortem_judgment_class_id: str,
        policy_learning_evidence_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningEvidenceAdmissionTemplateDefinition, bool]:
        """Return the matching evidence-admission template and fallback status."""

    def get_policy_learning_evidence_class(
        self,
        policy_learning_evidence_class_id: str,
    ) -> PolicyLearningEvidenceAdmissionClassDefinition:
        """Return the named policy-learning evidence class."""


class JsonPolicyLearningEvidenceAdmissionRegistry:
    """Loads policy-learning evidence-admission classes and templates."""

    def __init__(
        self,
        *,
        policy_learning_evidence_classes_path: Path,
        policy_learning_evidence_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._policy_learning_evidence_classes = self._load_classes(
            policy_learning_evidence_classes_path
        )
        self._policy_learning_evidence_templates = self._load_templates(
            policy_learning_evidence_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        post_mortem_judgment_class_id: str,
        policy_learning_evidence_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningEvidenceAdmissionTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._policy_learning_evidence_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.post_mortem_judgment_class_id == post_mortem_judgment_class_id
            and template.policy_learning_evidence_class_id
            == policy_learning_evidence_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.policy_learning_evidence_template_id,
            )[0]
            return (
                template,
                template.policy_learning_evidence_admission_status
                == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._policy_learning_evidence_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.post_mortem_judgment_class_id == post_mortem_judgment_class_id
            and template.policy_learning_evidence_class_id
            == policy_learning_evidence_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.policy_learning_evidence_template_id,
            )[0]
            return (
                template,
                template.policy_learning_evidence_admission_status
                == "fallback_template_applied",
            )

        raise PolicyLearningEvidenceAdmissionRegistryError(
            "No governed policy-learning evidence template applies to "
            f"policy_learning_evidence_class_id='{policy_learning_evidence_class_id}' "
            f"for post_mortem_judgment_class_id='{post_mortem_judgment_class_id}' "
            f"and route_name='{route_name}'."
        )

    def get_policy_learning_evidence_class(
        self,
        policy_learning_evidence_class_id: str,
    ) -> PolicyLearningEvidenceAdmissionClassDefinition:
        try:
            return self._policy_learning_evidence_classes[
                policy_learning_evidence_class_id
            ]
        except KeyError as error:
            raise PolicyLearningEvidenceAdmissionRegistryError(
                "Policy-learning evidence class "
                f"'{policy_learning_evidence_class_id}' is not registered."
            ) from error

    def _load_classes(
        self,
        policy_learning_evidence_classes_path: Path,
    ) -> dict[str, PolicyLearningEvidenceAdmissionClassDefinition]:
        content = json.loads(
            policy_learning_evidence_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, PolicyLearningEvidenceAdmissionClassDefinition] = {}
        for class_id, entry in content["policy_learning_evidence_classes"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_evidence_admission_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_evidence_admission_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_evidence_class_id"] != class_id:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence class key "
                    f"'{class_id}' must match policy_learning_evidence_class_id "
                    f"'{entry['policy_learning_evidence_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            if not entry["allowed_post_mortem_judgment_class_ids"]:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence class "
                    f"'{class_id}' must allow at least one post-mortem class."
                )
            invalid_post_mortem_classes = sorted(
                set(entry["allowed_post_mortem_judgment_class_ids"])
                - _VALID_POST_MORTEM_JUDGMENT_CLASS_IDS
            )
            if invalid_post_mortem_classes:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence class "
                    f"'{class_id}' references unknown post-mortem classes: "
                    + ", ".join(invalid_post_mortem_classes)
                    + "."
                )
            invalid_post_mortem_statuses = sorted(
                set(entry["allowed_post_mortem_statuses"])
                - _VALID_POST_MORTEM_STATUSES
            )
            if invalid_post_mortem_statuses:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence class "
                    f"'{class_id}' has invalid allowed_post_mortem_statuses: "
                    + ", ".join(invalid_post_mortem_statuses)
                    + "."
                )
            if entry["minimum_evidence_quality"] not in _VALID_EVIDENCE_QUALITIES:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence class "
                    f"'{class_id}' has invalid minimum_evidence_quality "
                    f"'{entry['minimum_evidence_quality']}'."
                )
            if entry["minimum_confidence_posture"] not in _VALID_CONFIDENCE_POSTURES:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence class "
                    f"'{class_id}' has invalid minimum_confidence_posture "
                    f"'{entry['minimum_confidence_posture']}'."
                )
            class_definitions[class_id] = PolicyLearningEvidenceAdmissionClassDefinition(
                policy_learning_evidence_class_id=entry[
                    "policy_learning_evidence_class_id"
                ],
                description=entry["description"],
                allowed_post_mortem_judgment_class_ids=tuple(
                    entry["allowed_post_mortem_judgment_class_ids"]
                ),
                allowed_post_mortem_statuses=tuple(
                    entry["allowed_post_mortem_statuses"]
                ),
                minimum_evidence_quality=entry["minimum_evidence_quality"],
                minimum_confidence_posture=entry["minimum_confidence_posture"],
                prohibited_evidence_fields=tuple(entry["prohibited_evidence_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_templates(
        self,
        policy_learning_evidence_templates_path: Path,
    ) -> tuple[PolicyLearningEvidenceAdmissionTemplateDefinition, ...]:
        content = json.loads(
            policy_learning_evidence_templates_path.read_text(encoding="utf-8")
        )
        templates: list[PolicyLearningEvidenceAdmissionTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content[
            "policy_learning_evidence_admission_templates"
        ].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_evidence_admission_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_evidence_admission_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_evidence_template_id"] != template_id:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence template key "
                    f"'{template_id}' must match policy_learning_evidence_template_id "
                    f"'{entry['policy_learning_evidence_template_id']}'."
                )
            if template_id in template_ids:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Duplicate policy_learning_evidence_template_id "
                    f"'{template_id}' found in policy-learning template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["policy_learning_evidence_admission_status"]
                not in _VALID_ADMISSION_STATUSES
            ):
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence template "
                    f"'{template_id}' has invalid policy_learning_evidence_admission_status "
                    f"'{entry['policy_learning_evidence_admission_status']}'."
                )
            if (
                entry["policy_learning_evidence_admission_outcome"]
                not in _VALID_ADMISSION_OUTCOMES
            ):
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence template "
                    f"'{template_id}' has invalid policy_learning_evidence_admission_outcome "
                    f"'{entry['policy_learning_evidence_admission_outcome']}'."
                )
            templates.append(
                PolicyLearningEvidenceAdmissionTemplateDefinition(
                    policy_learning_evidence_template_id=entry[
                        "policy_learning_evidence_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    post_mortem_judgment_class_id=entry[
                        "post_mortem_judgment_class_id"
                    ],
                    policy_learning_evidence_class_id=entry[
                        "policy_learning_evidence_class_id"
                    ],
                    required_evidence_fields=tuple(entry["required_evidence_fields"]),
                    optional_evidence_fields=tuple(entry["optional_evidence_fields"]),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    policy_learning_evidence_admission_status=entry[
                        "policy_learning_evidence_admission_status"
                    ],
                    policy_learning_evidence_admission_outcome=entry[
                        "policy_learning_evidence_admission_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._policy_learning_evidence_templates:
            class_definition = self._policy_learning_evidence_classes.get(
                template.policy_learning_evidence_class_id
            )
            if class_definition is None:
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence template "
                    f"'{template.policy_learning_evidence_template_id}' references unknown "
                    f"policy_learning_evidence_class_id '{template.policy_learning_evidence_class_id}'."
                )
            if (
                template.post_mortem_judgment_class_id
                not in class_definition.allowed_post_mortem_judgment_class_ids
            ):
                raise PolicyLearningEvidenceAdmissionRegistryError(
                    "Policy-learning evidence template "
                    f"'{template.policy_learning_evidence_template_id}' references "
                    f"post_mortem_judgment_class_id '{template.post_mortem_judgment_class_id}' "
                    f"that is not allowed by policy_learning_evidence_class_id "
                    f"'{template.policy_learning_evidence_class_id}'."
                )
