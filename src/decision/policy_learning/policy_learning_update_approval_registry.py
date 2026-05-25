from __future__ import annotations

"""Registry-backed policy-learning update-approval classes and templates.

Canon ownership:
- Owns governed update-approval identity and template identity for the
  narrow gate that sits downstream of a non-blocked policy-learning
  update-threshold record.
- Does not redefine update-threshold judgment, policy mutation,
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
_VALID_UPDATE_THRESHOLD_STATUSES = {
    "threshold_met",
    "fallback_template_applied",
}
_VALID_UPDATE_DECISION_OUTCOMES = {
    "accepted",
    "accepted_with_narrowed_scope",
    "deferred_for_continued_monitoring",
    "rejected",
}
_VALID_EVIDENCE_SUFFICIENCY = {
    "sufficient_for_proposed_update",
    "sufficient_only_for_narrowed_scope",
    "insufficient_pending_more_evidence",
    "threshold_evidence_incomplete",
    "threshold_evidence_overlap_prohibited",
    "insufficient_for_update_threshold",
}
_VALID_WEAK_EVIDENCE_CHECKS = {
    "weak_evidence_check_passed",
    "weak_evidence_check_requires_narrowing",
    "weak_evidence_check_requires_monitoring",
    "weak_evidence_check_blocked_for_overlap",
    "weak_evidence_check_failed",
}
_VALID_DIMENSION_STRENGTH = {"weak", "moderate", "strong"}
_VALID_UPDATE_APPROVAL_STATUSES = {
    "approval_ready",
    "fallback_template_applied",
}
_VALID_UPDATE_APPROVAL_OUTCOMES = {
    "approved_for_policy_update_preparation",
    "approved_with_restrictions",
    "deferred_pending_additional_governance",
}


class PolicyLearningUpdateApprovalRegistryError(ValueError):
    """Base error for policy-learning update-approval registry failures."""


@dataclass(frozen=True)
class PolicyLearningUpdateApprovalClassDefinition:
    policy_learning_update_approval_class_id: str
    description: str
    allowed_policy_learning_update_threshold_statuses: tuple[str, ...]
    allowed_policy_learning_update_decision_outcomes: tuple[str, ...]
    minimum_evidence_sufficiency: str
    minimum_weak_evidence_check: str
    minimum_dimension_strength: str
    allow_preparation_restrictions: bool
    allow_additional_governance_deferral: bool
    prohibited_update_approval_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PolicyLearningUpdateApprovalTemplateDefinition:
    policy_learning_update_approval_template_id: str
    semantic_scope: str
    policy_learning_update_threshold_class_id: str
    policy_learning_update_approval_class_id: str
    required_update_approval_fields: tuple[str, ...]
    optional_update_approval_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    policy_learning_update_approval_status: str
    policy_learning_update_approval_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PolicyLearningUpdateApprovalRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_threshold_class_id: str,
        policy_learning_update_approval_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdateApprovalTemplateDefinition, bool]:
        """Return the matching update-approval template and fallback status."""

    def get_policy_learning_update_approval_class(
        self,
        policy_learning_update_approval_class_id: str,
    ) -> PolicyLearningUpdateApprovalClassDefinition:
        """Return the named policy-learning update-approval class."""


class JsonPolicyLearningUpdateApprovalRegistry:
    """Loads policy-learning update-approval classes and templates."""

    def __init__(
        self,
        *,
        policy_learning_update_approval_classes_path: Path,
        policy_learning_update_approval_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._policy_learning_update_approval_classes = self._load_classes(
            policy_learning_update_approval_classes_path
        )
        self._policy_learning_update_approval_templates = self._load_templates(
            policy_learning_update_approval_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_threshold_class_id: str,
        policy_learning_update_approval_class_id: str,
        route_name: str | None,
    ) -> tuple[PolicyLearningUpdateApprovalTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._policy_learning_update_approval_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_threshold_class_id
            == policy_learning_update_threshold_class_id
            and template.policy_learning_update_approval_class_id
            == policy_learning_update_approval_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.policy_learning_update_approval_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_approval_status
                == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._policy_learning_update_approval_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_threshold_class_id
            == policy_learning_update_threshold_class_id
            and template.policy_learning_update_approval_class_id
            == policy_learning_update_approval_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.policy_learning_update_approval_template_id,
            )[0]
            return (
                template,
                template.policy_learning_update_approval_status
                == "fallback_template_applied",
            )

        raise PolicyLearningUpdateApprovalRegistryError(
            "No governed policy-learning update-approval template applies to "
            f"policy_learning_update_approval_class_id='"
            f"{policy_learning_update_approval_class_id}' for "
            f"policy_learning_update_threshold_class_id='"
            f"{policy_learning_update_threshold_class_id}' and route_name='"
            f"{route_name}'."
        )

    def get_policy_learning_update_approval_class(
        self,
        policy_learning_update_approval_class_id: str,
    ) -> PolicyLearningUpdateApprovalClassDefinition:
        try:
            return self._policy_learning_update_approval_classes[
                policy_learning_update_approval_class_id
            ]
        except KeyError as error:
            raise PolicyLearningUpdateApprovalRegistryError(
                "Policy-learning update-approval class "
                f"'{policy_learning_update_approval_class_id}' is not registered."
            ) from error

    def _load_classes(
        self,
        policy_learning_update_approval_classes_path: Path,
    ) -> dict[str, PolicyLearningUpdateApprovalClassDefinition]:
        content = json.loads(
            policy_learning_update_approval_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, PolicyLearningUpdateApprovalClassDefinition] = {}
        for class_id, entry in content["policy_learning_update_approval_classes"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_approval_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_approval_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_approval_class_id"] != class_id:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval class key "
                    f"'{class_id}' must match "
                    "policy_learning_update_approval_class_id "
                    f"'{entry['policy_learning_update_approval_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            if not entry["allowed_policy_learning_update_threshold_statuses"]:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval class "
                    f"'{class_id}' must allow at least one threshold status."
                )
            invalid_threshold_statuses = sorted(
                set(entry["allowed_policy_learning_update_threshold_statuses"])
                - _VALID_UPDATE_THRESHOLD_STATUSES
            )
            if invalid_threshold_statuses:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval class "
                    f"'{class_id}' has invalid "
                    "allowed_policy_learning_update_threshold_statuses: "
                    + ", ".join(invalid_threshold_statuses)
                    + "."
                )
            invalid_decision_outcomes = sorted(
                set(entry["allowed_policy_learning_update_decision_outcomes"])
                - _VALID_UPDATE_DECISION_OUTCOMES
            )
            if invalid_decision_outcomes:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval class "
                    f"'{class_id}' has invalid "
                    "allowed_policy_learning_update_decision_outcomes: "
                    + ", ".join(invalid_decision_outcomes)
                    + "."
                )
            if entry["minimum_evidence_sufficiency"] not in _VALID_EVIDENCE_SUFFICIENCY:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval class "
                    f"'{class_id}' has invalid minimum_evidence_sufficiency "
                    f"'{entry['minimum_evidence_sufficiency']}'."
                )
            if entry["minimum_weak_evidence_check"] not in _VALID_WEAK_EVIDENCE_CHECKS:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval class "
                    f"'{class_id}' has invalid minimum_weak_evidence_check "
                    f"'{entry['minimum_weak_evidence_check']}'."
                )
            if entry["minimum_dimension_strength"] not in _VALID_DIMENSION_STRENGTH:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval class "
                    f"'{class_id}' has invalid minimum_dimension_strength "
                    f"'{entry['minimum_dimension_strength']}'."
                )
            class_definitions[class_id] = PolicyLearningUpdateApprovalClassDefinition(
                policy_learning_update_approval_class_id=entry[
                    "policy_learning_update_approval_class_id"
                ],
                description=entry["description"],
                allowed_policy_learning_update_threshold_statuses=tuple(
                    entry["allowed_policy_learning_update_threshold_statuses"]
                ),
                allowed_policy_learning_update_decision_outcomes=tuple(
                    entry["allowed_policy_learning_update_decision_outcomes"]
                ),
                minimum_evidence_sufficiency=entry["minimum_evidence_sufficiency"],
                minimum_weak_evidence_check=entry["minimum_weak_evidence_check"],
                minimum_dimension_strength=entry["minimum_dimension_strength"],
                allow_preparation_restrictions=entry[
                    "allow_preparation_restrictions"
                ],
                allow_additional_governance_deferral=entry[
                    "allow_additional_governance_deferral"
                ],
                prohibited_update_approval_fields=tuple(
                    entry["prohibited_update_approval_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_templates(
        self,
        policy_learning_update_approval_templates_path: Path,
    ) -> tuple[PolicyLearningUpdateApprovalTemplateDefinition, ...]:
        content = json.loads(
            policy_learning_update_approval_templates_path.read_text(
                encoding="utf-8"
            )
        )
        templates: list[PolicyLearningUpdateApprovalTemplateDefinition] = []
        for template_id, entry in content["policy_learning_update_approval_templates"].items():
            self._contract_validator.validate_or_raise(
                "policy_learning_update_approval_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="policy_learning_update_approval_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["policy_learning_update_approval_template_id"] != template_id:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval template key "
                    f"'{template_id}' must match "
                    "policy_learning_update_approval_template_id "
                    f"'{entry['policy_learning_update_approval_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["policy_learning_update_approval_status"]
                not in _VALID_UPDATE_APPROVAL_STATUSES
            ):
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval template "
                    f"'{template_id}' has invalid policy_learning_update_approval_status "
                    f"'{entry['policy_learning_update_approval_status']}'."
                )
            if (
                entry["policy_learning_update_approval_outcome"]
                not in _VALID_UPDATE_APPROVAL_OUTCOMES
            ):
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval template "
                    f"'{template_id}' has invalid policy_learning_update_approval_outcome "
                    f"'{entry['policy_learning_update_approval_outcome']}'."
                )
            templates.append(
                PolicyLearningUpdateApprovalTemplateDefinition(
                    policy_learning_update_approval_template_id=entry[
                        "policy_learning_update_approval_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    policy_learning_update_threshold_class_id=entry[
                        "policy_learning_update_threshold_class_id"
                    ],
                    policy_learning_update_approval_class_id=entry[
                        "policy_learning_update_approval_class_id"
                    ],
                    required_update_approval_fields=tuple(
                        entry["required_update_approval_fields"]
                    ),
                    optional_update_approval_fields=tuple(
                        entry["optional_update_approval_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    policy_learning_update_approval_status=entry[
                        "policy_learning_update_approval_status"
                    ],
                    policy_learning_update_approval_outcome=entry[
                        "policy_learning_update_approval_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._policy_learning_update_approval_templates:
            if (
                template.policy_learning_update_approval_class_id
                not in self._policy_learning_update_approval_classes
            ):
                raise PolicyLearningUpdateApprovalRegistryError(
                    "Policy-learning update-approval template "
                    f"'{template.policy_learning_update_approval_template_id}' "
                    "references unknown policy_learning_update_approval_class_id "
                    f"'{template.policy_learning_update_approval_class_id}'."
                )
