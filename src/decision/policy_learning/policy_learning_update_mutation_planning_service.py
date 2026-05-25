from __future__ import annotations

"""Governed policy-learning update mutation planning.

Canon ownership:
- Consumes a governed policy-learning update-preparation record and explicit
    mutation-planning context to decide whether mutation planning is ready,
    ready with restrictions, deferred, blocked for missing context, rejected
    for mutation-planning use, or blocked for prohibited overlap.
- Does not own actual policy mutation execution, rollout or deployment
    execution, retraining execution, monitoring, reopen handling,
    orchestration meaning, lifecycle state meaning, preparation judgment,
    approval judgment, evidence admission, or threshold judgment.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping
from uuid import uuid4

from decision.policy_learning.policy_learning_update_preparation_service import (
    PolicyLearningUpdatePreparationRecord,
)
from decision.policy_learning.policy_learning_update_mutation_planning_audit_adapter import (
    PolicyLearningUpdateMutationPlanningAuditAdapter,
)
from decision.policy_learning.policy_learning_update_mutation_planning_registry import (
    PolicyLearningUpdateMutationPlanningRegistry,
)

_DIMENSION_STRENGTH_RANK = {"weak": 0, "moderate": 1, "strong": 2}
_DIMENSION_FIELDS = (
    "boundary_control_strength",
    "preparation_readiness",
    "artifact_readiness",
    "planning_readiness",
    "prerequisite_readiness",
    "mutation_readiness",
    "safeguard_readiness",
    "rollback_readiness",
)


@dataclass(frozen=True)
class PolicyLearningUpdateMutationPlanningRequest:
    policy_learning_update_preparation: PolicyLearningUpdatePreparationRecord
    policy_learning_update_mutation_planning_class_id: str
    policy_learning_update_mutation_planning_author_role: str
    policy_learning_update_mutation_planning_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class PolicyLearningUpdateMutationPlanningRecord:
    policy_learning_update_mutation_planning_id: str
    policy_learning_update_mutation_planning_status: str
    reason: str
    policy_learning_update_mutation_planning_class_id: str
    policy_learning_update_mutation_planning_template_id: str
    policy_learning_update_mutation_planning_outcome: str
    artifact_readiness: str
    planning_readiness: str
    prerequisite_readiness: str
    mutation_readiness: str
    safeguard_readiness: str
    rollback_readiness: str
    preparation_package_reference: str
    preparation_summary: str
    mutation_planning_scope_reference: str
    preparation_artifact_boundary_summary: str
    mutation_plan_reference: str
    mutation_planning_summary: str
    mutation_plan_scope_reference: str
    mutation_planning_boundary_summary: str
    policy_learning_update_preparation_id: str
    policy_learning_update_preparation_status: str
    policy_learning_update_preparation_class_id: str
    policy_learning_update_preparation_template_id: str
    policy_learning_update_preparation_outcome: str
    policy_learning_update_approval_id: str
    policy_learning_update_approval_status: str
    policy_learning_update_approval_class_id: str
    policy_learning_update_approval_template_id: str
    policy_learning_update_approval_outcome: str
    governance_readiness: str
    change_control_readiness: str
    boundary_control_strength: str
    preparation_readiness: str
    candidate_update_reference: str
    approval_summary: str
    change_control_reference: str
    preparation_scope_reference: str
    preparation_boundary_summary: str
    policy_learning_update_threshold_id: str
    policy_learning_update_threshold_status: str
    policy_learning_update_threshold_class_id: str
    policy_learning_update_threshold_template_id: str
    policy_learning_update_decision_outcome: str
    evidence_sufficiency: str
    weak_evidence_check: str
    policy_behavior_change: str
    update_severity: str
    update_scope: str
    policy_learning_evidence_admission_id: str
    policy_learning_evidence_admission_status: str
    policy_learning_evidence_class_id: str
    policy_learning_evidence_template_id: str
    policy_learning_evidence_admission_outcome: str
    post_mortem_judgment_id: str
    post_mortem_judgment_status: str
    post_mortem_judgment_class_id: str
    post_mortem_judgment_template_id: str
    execution_outcome_id: str
    execution_outcome_status: str
    execution_outcome_class_id: str
    execution_dispatch_id: str
    execution_dispatch_class_id: str
    execution_request_id: str
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    policy_learning_update_threshold_author_role: str
    policy_learning_update_threshold_author_id: str
    policy_learning_update_approval_author_role: str
    policy_learning_update_approval_author_id: str
    policy_learning_update_preparation_author_role: str
    policy_learning_update_preparation_author_id: str
    policy_learning_update_mutation_planning_author_role: str
    policy_learning_update_mutation_planning_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_update_mutation_planning_fields: tuple[str, ...]
    optional_update_mutation_planning_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_update_mutation_planning_fields: tuple[str, ...]
    required_update_mutation_planning_snapshot: Mapping[str, str]
    optional_update_mutation_planning_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    domain_reference: str | None = None
    decision_scope_reference: str | None = None
    reporting_scope_reference: str | None = None
    tenant_scope_reference: str | None = None
    learning_scope_reference: str | None = None
    restriction_summary: str | None = None
    mutation_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    mutation_planning_prerequisite_reference: str | None = None
    outstanding_mutation_planning_prerequisites: tuple[str, ...] = ()
    missing_update_mutation_planning_fields: tuple[str, ...] = ()
    prohibited_update_mutation_planning_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "policy_learning_update_mutation_planning_id": self.policy_learning_update_mutation_planning_id,
            "policy_learning_update_mutation_planning_status": self.policy_learning_update_mutation_planning_status,
            "reason": self.reason,
            "policy_learning_update_mutation_planning_class_id": self.policy_learning_update_mutation_planning_class_id,
            "policy_learning_update_mutation_planning_template_id": self.policy_learning_update_mutation_planning_template_id,
            "policy_learning_update_mutation_planning_outcome": self.policy_learning_update_mutation_planning_outcome,
            "artifact_readiness": self.artifact_readiness,
            "planning_readiness": self.planning_readiness,
            "prerequisite_readiness": self.prerequisite_readiness,
            "mutation_readiness": self.mutation_readiness,
            "safeguard_readiness": self.safeguard_readiness,
            "rollback_readiness": self.rollback_readiness,
            "preparation_package_reference": self.preparation_package_reference,
            "preparation_summary": self.preparation_summary,
            "mutation_planning_scope_reference": self.mutation_planning_scope_reference,
            "preparation_artifact_boundary_summary": self.preparation_artifact_boundary_summary,
            "mutation_plan_reference": self.mutation_plan_reference,
            "mutation_planning_summary": self.mutation_planning_summary,
            "mutation_plan_scope_reference": self.mutation_plan_scope_reference,
            "mutation_planning_boundary_summary": self.mutation_planning_boundary_summary,
            "policy_learning_update_preparation_id": self.policy_learning_update_preparation_id,
            "policy_learning_update_preparation_status": self.policy_learning_update_preparation_status,
            "policy_learning_update_preparation_class_id": self.policy_learning_update_preparation_class_id,
            "policy_learning_update_preparation_template_id": self.policy_learning_update_preparation_template_id,
            "policy_learning_update_preparation_outcome": self.policy_learning_update_preparation_outcome,
            "policy_learning_update_approval_id": self.policy_learning_update_approval_id,
            "policy_learning_update_approval_status": self.policy_learning_update_approval_status,
            "policy_learning_update_approval_class_id": self.policy_learning_update_approval_class_id,
            "policy_learning_update_approval_template_id": self.policy_learning_update_approval_template_id,
            "policy_learning_update_approval_outcome": self.policy_learning_update_approval_outcome,
            "governance_readiness": self.governance_readiness,
            "change_control_readiness": self.change_control_readiness,
            "boundary_control_strength": self.boundary_control_strength,
            "preparation_readiness": self.preparation_readiness,
            "candidate_update_reference": self.candidate_update_reference,
            "approval_summary": self.approval_summary,
            "change_control_reference": self.change_control_reference,
            "preparation_scope_reference": self.preparation_scope_reference,
            "preparation_boundary_summary": self.preparation_boundary_summary,
            "policy_learning_update_threshold_id": self.policy_learning_update_threshold_id,
            "policy_learning_update_threshold_status": self.policy_learning_update_threshold_status,
            "policy_learning_update_threshold_class_id": self.policy_learning_update_threshold_class_id,
            "policy_learning_update_threshold_template_id": self.policy_learning_update_threshold_template_id,
            "policy_learning_update_decision_outcome": self.policy_learning_update_decision_outcome,
            "evidence_sufficiency": self.evidence_sufficiency,
            "weak_evidence_check": self.weak_evidence_check,
            "policy_behavior_change": self.policy_behavior_change,
            "update_severity": self.update_severity,
            "update_scope": self.update_scope,
            "policy_learning_evidence_admission_id": self.policy_learning_evidence_admission_id,
            "policy_learning_evidence_admission_status": self.policy_learning_evidence_admission_status,
            "policy_learning_evidence_class_id": self.policy_learning_evidence_class_id,
            "policy_learning_evidence_template_id": self.policy_learning_evidence_template_id,
            "policy_learning_evidence_admission_outcome": self.policy_learning_evidence_admission_outcome,
            "post_mortem_judgment_id": self.post_mortem_judgment_id,
            "post_mortem_judgment_status": self.post_mortem_judgment_status,
            "post_mortem_judgment_class_id": self.post_mortem_judgment_class_id,
            "post_mortem_judgment_template_id": self.post_mortem_judgment_template_id,
            "execution_outcome_id": self.execution_outcome_id,
            "execution_outcome_status": self.execution_outcome_status,
            "execution_outcome_class_id": self.execution_outcome_class_id,
            "execution_dispatch_id": self.execution_dispatch_id,
            "execution_dispatch_class_id": self.execution_dispatch_class_id,
            "execution_request_id": self.execution_request_id,
            "semantic_scope": self.semantic_scope,
            "case_type": self.case_type,
            "case_key": self.case_key,
            "state_model_name": self.state_model_name,
            "episode_id": self.episode_id,
            "transition_name": self.transition_name,
            "transition_class": self.transition_class,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "policy_learning_update_threshold_author_role": self.policy_learning_update_threshold_author_role,
            "policy_learning_update_threshold_author_id": self.policy_learning_update_threshold_author_id,
            "policy_learning_update_approval_author_role": self.policy_learning_update_approval_author_role,
            "policy_learning_update_approval_author_id": self.policy_learning_update_approval_author_id,
            "policy_learning_update_preparation_author_role": self.policy_learning_update_preparation_author_role,
            "policy_learning_update_preparation_author_id": self.policy_learning_update_preparation_author_id,
            "policy_learning_update_mutation_planning_author_role": self.policy_learning_update_mutation_planning_author_role,
            "policy_learning_update_mutation_planning_author_id": self.policy_learning_update_mutation_planning_author_id,
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "required_update_mutation_planning_fields": list(self.required_update_mutation_planning_fields),
            "optional_update_mutation_planning_fields": list(self.optional_update_mutation_planning_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_update_mutation_planning_fields": list(self.prohibited_update_mutation_planning_fields),
            "required_update_mutation_planning_snapshot": dict(self.required_update_mutation_planning_snapshot),
            "optional_update_mutation_planning_snapshot": dict(self.optional_update_mutation_planning_snapshot),
            "required_audit_snapshot": dict(self.required_audit_snapshot),
            "lineage": dict(self.lineage),
            "generated_at": self.generated_at.isoformat(),
        }
        if self.domain_reference is not None:
            payload["domain_reference"] = self.domain_reference
        if self.decision_scope_reference is not None:
            payload["decision_scope_reference"] = self.decision_scope_reference
        if self.reporting_scope_reference is not None:
            payload["reporting_scope_reference"] = self.reporting_scope_reference
        if self.tenant_scope_reference is not None:
            payload["tenant_scope_reference"] = self.tenant_scope_reference
        if self.learning_scope_reference is not None:
            payload["learning_scope_reference"] = self.learning_scope_reference
        if self.restriction_summary is not None:
            payload["restriction_summary"] = self.restriction_summary
        if self.mutation_scope_restriction_reference is not None:
            payload["mutation_scope_restriction_reference"] = (
                self.mutation_scope_restriction_reference
            )
        if self.follow_up_review_reference is not None:
            payload["follow_up_review_reference"] = self.follow_up_review_reference
        if self.mutation_planning_prerequisite_reference is not None:
            payload["mutation_planning_prerequisite_reference"] = (
                self.mutation_planning_prerequisite_reference
            )
        if self.outstanding_mutation_planning_prerequisites:
            payload["outstanding_mutation_planning_prerequisites"] = list(
                self.outstanding_mutation_planning_prerequisites
            )
        if self.missing_update_mutation_planning_fields:
            payload["missing_update_mutation_planning_fields"] = list(
                self.missing_update_mutation_planning_fields
            )
        if self.prohibited_update_mutation_planning_fields_present:
            payload["prohibited_update_mutation_planning_fields_present"] = list(
                self.prohibited_update_mutation_planning_fields_present
            )
        return payload

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "policy_learning_update_mutation_planning_outcome": (
                self.policy_learning_update_mutation_planning_outcome
            ),
            "mutation_plan_reference": self.mutation_plan_reference,
            "mutation_plan_scope_reference": self.mutation_plan_scope_reference,
        }
        if self.restriction_summary is not None:
            context["restriction_summary"] = self.restriction_summary
        if self.mutation_scope_restriction_reference is not None:
            context["mutation_scope_restriction_reference"] = (
                self.mutation_scope_restriction_reference
            )
        if self.follow_up_review_reference is not None:
            context["follow_up_review_reference"] = self.follow_up_review_reference
        if self.mutation_planning_prerequisite_reference is not None:
            context["mutation_planning_prerequisite_reference"] = (
                self.mutation_planning_prerequisite_reference
            )
        if self.outstanding_mutation_planning_prerequisites:
            context["outstanding_mutation_planning_prerequisites"] = list(
                self.outstanding_mutation_planning_prerequisites
            )
        return context


class PolicyLearningUpdateMutationPlanningService:
    """Builds policy-learning update-mutation-planning records from preparation records."""

    def __init__(
        self,
        *,
        policy_learning_update_mutation_planning_registry: PolicyLearningUpdateMutationPlanningRegistry,
        policy_learning_update_mutation_planning_audit_adapter: PolicyLearningUpdateMutationPlanningAuditAdapter,
    ) -> None:
        self._policy_learning_update_mutation_planning_registry = (
            policy_learning_update_mutation_planning_registry
        )
        self._policy_learning_update_mutation_planning_audit_adapter = (
            policy_learning_update_mutation_planning_audit_adapter
        )

    def generate(
        self,
        request: PolicyLearningUpdateMutationPlanningRequest,
    ) -> PolicyLearningUpdateMutationPlanningRecord:
        template, fallback_template_used = (
            self._policy_learning_update_mutation_planning_registry.resolve_template(
                semantic_scope=request.policy_learning_update_preparation.semantic_scope,
                policy_learning_update_preparation_class_id=(
                    request.policy_learning_update_preparation.policy_learning_update_preparation_class_id
                ),
                policy_learning_update_mutation_planning_class_id=(
                    request.policy_learning_update_mutation_planning_class_id
                ),
                route_name=request.policy_learning_update_preparation.lineage.get(
                    "route_name"
                ),
            )
        )
        class_definition = (
            self._policy_learning_update_mutation_planning_registry.get_policy_learning_update_mutation_planning_class(
                request.policy_learning_update_mutation_planning_class_id
            )
        )
        combined_context = self._combined_context(request, class_definition)
        required_update_mutation_planning_snapshot, missing_update_mutation_planning_fields = (
            self._snapshot_required_fields(
                template.required_update_mutation_planning_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_update_mutation_planning_fields + missing_audit_fields)
        )
        optional_update_mutation_planning_snapshot = self._snapshot_optional_fields(
            template.optional_update_mutation_planning_fields,
            combined_context,
        )
        prohibited_update_mutation_planning_fields_present = (
            self._prohibited_update_mutation_planning_fields_present(
                class_definition.prohibited_update_mutation_planning_fields,
                request.policy_learning_update_mutation_planning_context,
            )
        )
        mutation_planning_status = self._mutation_planning_status(
            policy_learning_update_preparation=request.policy_learning_update_preparation,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_update_mutation_planning_fields=all_missing_fields,
            prohibited_update_mutation_planning_fields_present=(
                prohibited_update_mutation_planning_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        mutation_planning_outcome = self._mutation_planning_outcome(
            template=template,
            mutation_planning_status=mutation_planning_status,
        )
        reason = self._reason(
            policy_learning_update_preparation=request.policy_learning_update_preparation,
            mutation_planning_status=mutation_planning_status,
            policy_learning_update_mutation_planning_class_id=(
                class_definition.policy_learning_update_mutation_planning_class_id
            ),
            missing_update_mutation_planning_fields=all_missing_fields,
            prohibited_update_mutation_planning_fields_present=(
                prohibited_update_mutation_planning_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            mutation_planning_outcome=mutation_planning_outcome,
        )
        lineage = self._lineage(request, class_definition, template)

        policy_learning_update_mutation_planning = PolicyLearningUpdateMutationPlanningRecord(
            policy_learning_update_mutation_planning_id=str(uuid4()),
            policy_learning_update_mutation_planning_status=mutation_planning_status,
            reason=reason,
            policy_learning_update_mutation_planning_class_id=(
                class_definition.policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_template_id=(
                template.policy_learning_update_mutation_planning_template_id
            ),
            policy_learning_update_mutation_planning_outcome=mutation_planning_outcome,
            artifact_readiness=self._field_value_or_placeholder(
                field_name="artifact_readiness",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            planning_readiness=self._field_value_or_placeholder(
                field_name="planning_readiness",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            prerequisite_readiness=self._field_value_or_placeholder(
                field_name="prerequisite_readiness",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            mutation_readiness=self._field_value_or_placeholder(
                field_name="mutation_readiness",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            safeguard_readiness=self._field_value_or_placeholder(
                field_name="safeguard_readiness",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            rollback_readiness=self._field_value_or_placeholder(
                field_name="rollback_readiness",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            preparation_package_reference=self._field_value_or_placeholder(
                field_name="preparation_package_reference",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            preparation_summary=self._field_value_or_placeholder(
                field_name="preparation_summary",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            mutation_planning_scope_reference=self._field_value_or_placeholder(
                field_name="mutation_planning_scope_reference",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            preparation_artifact_boundary_summary=self._field_value_or_placeholder(
                field_name="preparation_artifact_boundary_summary",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            mutation_plan_reference=self._field_value_or_placeholder(
                field_name="mutation_plan_reference",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            mutation_planning_summary=self._field_value_or_placeholder(
                field_name="mutation_planning_summary",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            mutation_plan_scope_reference=self._field_value_or_placeholder(
                field_name="mutation_plan_scope_reference",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            mutation_planning_boundary_summary=self._field_value_or_placeholder(
                field_name="mutation_planning_boundary_summary",
                snapshot=required_update_mutation_planning_snapshot,
                context=combined_context,
            ),
            policy_learning_update_preparation_id=(
                request.policy_learning_update_preparation.policy_learning_update_preparation_id
            ),
            policy_learning_update_preparation_status=(
                request.policy_learning_update_preparation.policy_learning_update_preparation_status
            ),
            policy_learning_update_preparation_class_id=(
                request.policy_learning_update_preparation.policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_template_id=(
                request.policy_learning_update_preparation.policy_learning_update_preparation_template_id
            ),
            policy_learning_update_preparation_outcome=(
                request.policy_learning_update_preparation.policy_learning_update_preparation_outcome
            ),
            policy_learning_update_approval_id=(
                request.policy_learning_update_preparation.policy_learning_update_approval_id
            ),
            policy_learning_update_approval_status=(
                request.policy_learning_update_preparation.policy_learning_update_approval_status
            ),
            policy_learning_update_approval_class_id=(
                request.policy_learning_update_preparation.policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_template_id=(
                request.policy_learning_update_preparation.policy_learning_update_approval_template_id
            ),
            policy_learning_update_approval_outcome=(
                request.policy_learning_update_preparation.policy_learning_update_approval_outcome
            ),
            governance_readiness=(
                request.policy_learning_update_preparation.governance_readiness
            ),
            change_control_readiness=(
                request.policy_learning_update_preparation.change_control_readiness
            ),
            boundary_control_strength=(
                request.policy_learning_update_preparation.boundary_control_strength
            ),
            preparation_readiness=(
                request.policy_learning_update_preparation.preparation_readiness
            ),
            candidate_update_reference=(
                request.policy_learning_update_preparation.candidate_update_reference
            ),
            approval_summary=request.policy_learning_update_preparation.approval_summary,
            change_control_reference=(
                request.policy_learning_update_preparation.change_control_reference
            ),
            preparation_scope_reference=(
                request.policy_learning_update_preparation.preparation_scope_reference
            ),
            preparation_boundary_summary=(
                request.policy_learning_update_preparation.preparation_boundary_summary
            ),
            policy_learning_update_threshold_id=(
                request.policy_learning_update_preparation.policy_learning_update_threshold_id
            ),
            policy_learning_update_threshold_status=(
                request.policy_learning_update_preparation.policy_learning_update_threshold_status
            ),
            policy_learning_update_threshold_class_id=(
                request.policy_learning_update_preparation.policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_template_id=(
                request.policy_learning_update_preparation.policy_learning_update_threshold_template_id
            ),
            policy_learning_update_decision_outcome=(
                request.policy_learning_update_preparation.policy_learning_update_decision_outcome
            ),
            evidence_sufficiency=request.policy_learning_update_preparation.evidence_sufficiency,
            weak_evidence_check=request.policy_learning_update_preparation.weak_evidence_check,
            policy_behavior_change=(
                request.policy_learning_update_preparation.policy_behavior_change
            ),
            update_severity=request.policy_learning_update_preparation.update_severity,
            update_scope=request.policy_learning_update_preparation.update_scope,
            policy_learning_evidence_admission_id=(
                request.policy_learning_update_preparation.policy_learning_evidence_admission_id
            ),
            policy_learning_evidence_admission_status=(
                request.policy_learning_update_preparation.policy_learning_evidence_admission_status
            ),
            policy_learning_evidence_class_id=(
                request.policy_learning_update_preparation.policy_learning_evidence_class_id
            ),
            policy_learning_evidence_template_id=(
                request.policy_learning_update_preparation.policy_learning_evidence_template_id
            ),
            policy_learning_evidence_admission_outcome=(
                request.policy_learning_update_preparation.policy_learning_evidence_admission_outcome
            ),
            post_mortem_judgment_id=(
                request.policy_learning_update_preparation.post_mortem_judgment_id
            ),
            post_mortem_judgment_status=(
                request.policy_learning_update_preparation.post_mortem_judgment_status
            ),
            post_mortem_judgment_class_id=(
                request.policy_learning_update_preparation.post_mortem_judgment_class_id
            ),
            post_mortem_judgment_template_id=(
                request.policy_learning_update_preparation.post_mortem_judgment_template_id
            ),
            execution_outcome_id=request.policy_learning_update_preparation.execution_outcome_id,
            execution_outcome_status=(
                request.policy_learning_update_preparation.execution_outcome_status
            ),
            execution_outcome_class_id=(
                request.policy_learning_update_preparation.execution_outcome_class_id
            ),
            execution_dispatch_id=(
                request.policy_learning_update_preparation.execution_dispatch_id
            ),
            execution_dispatch_class_id=(
                request.policy_learning_update_preparation.execution_dispatch_class_id
            ),
            execution_request_id=(
                request.policy_learning_update_preparation.execution_request_id
            ),
            semantic_scope=request.policy_learning_update_preparation.semantic_scope,
            case_type=request.policy_learning_update_preparation.case_type,
            case_key=request.policy_learning_update_preparation.case_key,
            state_model_name=request.policy_learning_update_preparation.state_model_name,
            episode_id=request.policy_learning_update_preparation.episode_id,
            transition_name=request.policy_learning_update_preparation.transition_name,
            transition_class=request.policy_learning_update_preparation.transition_class,
            source_stage=request.policy_learning_update_preparation.source_stage,
            target_stage=request.policy_learning_update_preparation.target_stage,
            policy_learning_update_threshold_author_role=(
                request.policy_learning_update_preparation.policy_learning_update_threshold_author_role
            ),
            policy_learning_update_threshold_author_id=(
                request.policy_learning_update_preparation.policy_learning_update_threshold_author_id
            ),
            policy_learning_update_approval_author_role=(
                request.policy_learning_update_preparation.policy_learning_update_approval_author_role
            ),
            policy_learning_update_approval_author_id=(
                request.policy_learning_update_preparation.policy_learning_update_approval_author_id
            ),
            policy_learning_update_preparation_author_role=(
                request.policy_learning_update_preparation.policy_learning_update_preparation_author_role
            ),
            policy_learning_update_preparation_author_id=(
                request.policy_learning_update_preparation.policy_learning_update_preparation_author_id
            ),
            policy_learning_update_mutation_planning_author_role=(
                request.policy_learning_update_mutation_planning_author_role
            ),
            policy_learning_update_mutation_planning_author_id=request.actor_id,
            authority_resolution_kind=(
                request.policy_learning_update_preparation.authority_resolution_kind
            ),
            authority_review_required=(
                request.policy_learning_update_preparation.authority_review_required
            ),
            router_rule_id=request.policy_learning_update_preparation.router_rule_id,
            routing_resolution_status=(
                request.policy_learning_update_preparation.routing_resolution_status
            ),
            routing_review_required=(
                request.policy_learning_update_preparation.routing_review_required
            ),
            review_mode=request.policy_learning_update_preparation.review_mode,
            required_update_mutation_planning_fields=(
                template.required_update_mutation_planning_fields
            ),
            optional_update_mutation_planning_fields=(
                template.optional_update_mutation_planning_fields
            ),
            required_audit_fields=template.required_audit_fields,
            prohibited_update_mutation_planning_fields=(
                class_definition.prohibited_update_mutation_planning_fields
            ),
            required_update_mutation_planning_snapshot=required_update_mutation_planning_snapshot,
            optional_update_mutation_planning_snapshot=optional_update_mutation_planning_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=lineage,
            generated_at=datetime.now(tz=UTC),
            domain_reference=self._optional_text(combined_context.get("domain_reference")),
            decision_scope_reference=self._optional_text(
                combined_context.get("decision_scope_reference")
            ),
            reporting_scope_reference=self._optional_text(
                combined_context.get("reporting_scope_reference")
            ),
            tenant_scope_reference=self._optional_text(
                combined_context.get("tenant_scope_reference")
            ),
            learning_scope_reference=self._optional_text(
                combined_context.get("learning_scope_reference")
            ),
            restriction_summary=self._optional_text(
                combined_context.get("restriction_summary")
            ),
            mutation_scope_restriction_reference=self._optional_text(
                combined_context.get("mutation_scope_restriction_reference")
            ),
            follow_up_review_reference=self._optional_text(
                combined_context.get("follow_up_review_reference")
            ),
            mutation_planning_prerequisite_reference=self._optional_text(
                combined_context.get("mutation_planning_prerequisite_reference")
            ),
            outstanding_mutation_planning_prerequisites=self._sequence_as_tuple(
                combined_context.get("outstanding_mutation_planning_prerequisites")
            ),
            missing_update_mutation_planning_fields=all_missing_fields,
            prohibited_update_mutation_planning_fields_present=(
                prohibited_update_mutation_planning_fields_present
            ),
        )
        self._policy_learning_update_mutation_planning_audit_adapter.record_policy_learning_update_mutation_planning(
            policy_learning_update_mutation_planning,
            request=request,
        )
        return policy_learning_update_mutation_planning

    def _combined_context(
        self,
        request: PolicyLearningUpdateMutationPlanningRequest,
        class_definition,
    ) -> dict[str, object]:
        context = dict(
            request.policy_learning_update_preparation.required_update_preparation_snapshot
        )
        context.update(
            request.policy_learning_update_preparation.optional_update_preparation_snapshot
        )
        context.update(request.policy_learning_update_preparation.required_audit_snapshot)
        context.update(dict(request.policy_learning_update_mutation_planning_context))
        context.update(
            {
                "policy_learning_update_mutation_planning_class_id": (
                    class_definition.policy_learning_update_mutation_planning_class_id
                ),
                "policy_learning_update_mutation_planning_author_id": request.actor_id,
                "policy_learning_update_mutation_planning_author_role": (
                    request.policy_learning_update_mutation_planning_author_role
                ),
                "policy_learning_update_preparation_id": (
                    request.policy_learning_update_preparation.policy_learning_update_preparation_id
                ),
                "policy_learning_update_preparation_status": (
                    request.policy_learning_update_preparation.policy_learning_update_preparation_status
                ),
                "policy_learning_update_preparation_class_id": (
                    request.policy_learning_update_preparation.policy_learning_update_preparation_class_id
                ),
                "policy_learning_update_preparation_template_id": (
                    request.policy_learning_update_preparation.policy_learning_update_preparation_template_id
                ),
                "policy_learning_update_preparation_outcome": (
                    request.policy_learning_update_preparation.policy_learning_update_preparation_outcome
                ),
                "boundary_control_strength": (
                    request.policy_learning_update_preparation.boundary_control_strength
                ),
                "preparation_readiness": (
                    request.policy_learning_update_preparation.preparation_readiness
                ),
                "artifact_readiness": (
                    request.policy_learning_update_preparation.artifact_readiness
                ),
                "planning_readiness": (
                    request.policy_learning_update_preparation.planning_readiness
                ),
                "prerequisite_readiness": (
                    request.policy_learning_update_preparation.prerequisite_readiness
                ),
                "preparation_package_reference": (
                    request.policy_learning_update_preparation.preparation_package_reference
                ),
                "preparation_summary": (
                    request.policy_learning_update_preparation.preparation_summary
                ),
                "preparation_artifact_boundary_summary": (
                    request.policy_learning_update_preparation.preparation_artifact_boundary_summary
                ),
                "domain_reference": self._optional_text(context.get("domain_reference"))
                or request.policy_learning_update_preparation.domain_reference
                or request.policy_learning_update_preparation.semantic_scope,
                "decision_scope_reference": self._optional_text(
                    context.get("decision_scope_reference")
                )
                or request.policy_learning_update_preparation.decision_scope_reference
                or "",
                "reporting_scope_reference": self._optional_text(
                    context.get("reporting_scope_reference")
                )
                or request.policy_learning_update_preparation.reporting_scope_reference
                or "",
                "tenant_scope_reference": self._optional_text(
                    context.get("tenant_scope_reference")
                )
                or request.policy_learning_update_preparation.tenant_scope_reference
                or "",
                "learning_scope_reference": self._optional_text(
                    context.get("learning_scope_reference")
                )
                or request.policy_learning_update_preparation.learning_scope_reference
                or request.policy_learning_update_preparation.update_scope,
                "candidate_update_reference": self._optional_text(
                    context.get("candidate_update_reference")
                )
                or request.policy_learning_update_preparation.candidate_update_reference,
                "restriction_summary": self._optional_text(
                    context.get("restriction_summary")
                )
                or request.policy_learning_update_preparation.restriction_summary,
                "mutation_scope_restriction_reference": self._optional_text(
                    context.get("mutation_scope_restriction_reference")
                )
                or request.policy_learning_update_preparation.preparation_scope_restriction_reference,
                "follow_up_review_reference": self._optional_text(
                    context.get("follow_up_review_reference")
                )
                or request.policy_learning_update_preparation.follow_up_review_reference,
                "mutation_planning_prerequisite_reference": self._optional_text(
                    context.get("mutation_planning_prerequisite_reference")
                )
                or request.policy_learning_update_preparation.preparation_prerequisite_reference,
                "outstanding_mutation_planning_prerequisites": (
                    self._sequence_as_tuple(
                        context.get("outstanding_mutation_planning_prerequisites")
                    )
                    or request.policy_learning_update_preparation.outstanding_preparation_prerequisites
                ),
                "mutation_planning_scope_reference": self._optional_text(
                    context.get("mutation_planning_scope_reference")
                )
                or request.policy_learning_update_preparation.preparation_scope_reference
                or request.policy_learning_update_preparation.learning_scope_reference,
                "mutation_plan_scope_reference": self._optional_text(
                    context.get("mutation_plan_scope_reference")
                )
                or self._optional_text(context.get("mutation_planning_scope_reference"))
                or request.policy_learning_update_preparation.preparation_scope_reference
                or request.policy_learning_update_preparation.learning_scope_reference,
            }
        )
        return context

    def _snapshot_required_fields(
        self,
        field_names: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[dict[str, str], tuple[str, ...]]:
        snapshot: dict[str, str] = {}
        missing_fields: list[str] = []
        for field_name in field_names:
            value = context.get(field_name)
            if self._is_missing_value(value):
                missing_fields.append(field_name)
                continue
            snapshot[field_name] = self._to_text(value)
        return snapshot, tuple(missing_fields)

    def _snapshot_optional_fields(
        self,
        field_names: tuple[str, ...],
        context: Mapping[str, object],
    ) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for field_name in field_names:
            value = context.get(field_name)
            if self._is_missing_value(value):
                continue
            snapshot[field_name] = self._to_text(value)
        return snapshot

    def _prohibited_update_mutation_planning_fields_present(
        self,
        field_names: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        present_fields: list[str] = []
        for field_name in field_names:
            value = context.get(field_name)
            if self._is_missing_value(value):
                continue
            present_fields.append(field_name)
        return tuple(present_fields)

    def _mutation_planning_status(
        self,
        *,
        policy_learning_update_preparation: PolicyLearningUpdatePreparationRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_update_mutation_planning_fields: tuple[str, ...],
        prohibited_update_mutation_planning_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_update_mutation_planning_fields_present:
            return "prohibited_overlap_blocked"
        if missing_update_mutation_planning_fields:
            return "blocked_missing_context"
        if self._below_mutation_planning_threshold(
            policy_learning_update_preparation,
            class_definition,
            combined_context,
        ):
            return "rejected_for_mutation_planning_use"
        if self._requires_mutation_planning_prerequisite_deferral(
            class_definition,
            combined_context,
        ):
            return "fallback_template_applied"
        if self._requires_mutation_planning_restrictions(
            policy_learning_update_preparation,
            class_definition,
            combined_context,
        ):
            return "fallback_template_applied"
        if fallback_template_used:
            return "fallback_template_applied"
        return "mutation_planning_ready"

    def _below_mutation_planning_threshold(
        self,
        policy_learning_update_preparation: PolicyLearningUpdatePreparationRecord,
        class_definition,
        combined_context: Mapping[str, object],
    ) -> bool:
        if (
            policy_learning_update_preparation.policy_learning_update_preparation_status
            not in class_definition.allowed_policy_learning_update_preparation_statuses
        ):
            return True
        if (
            policy_learning_update_preparation.policy_learning_update_preparation_outcome
            not in class_definition.allowed_policy_learning_update_preparation_outcomes
        ):
            return True
        if (
            self._dimension_strength_rank_from_context(combined_context)
            < self._dimension_strength_rank(
                class_definition.minimum_dimension_strength
            )
        ):
            return True

        restriction_summary = self._optional_text(
            combined_context.get("restriction_summary")
        )
        mutation_scope_restriction_reference = self._optional_text(
            combined_context.get("mutation_scope_restriction_reference")
        )
        if (
            (
                restriction_summary is not None
                or mutation_scope_restriction_reference is not None
                or policy_learning_update_preparation.policy_learning_update_preparation_outcome
                == "prepared_with_restrictions"
            )
            and not class_definition.allow_mutation_planning_restrictions
        ):
            return True

        mutation_planning_prerequisite_reference = self._optional_text(
            combined_context.get("mutation_planning_prerequisite_reference")
        )
        outstanding_mutation_planning_prerequisites = self._sequence_as_tuple(
            combined_context.get("outstanding_mutation_planning_prerequisites")
        )
        follow_up_review_reference = self._optional_text(
            combined_context.get("follow_up_review_reference")
        )
        if (
            (
                mutation_planning_prerequisite_reference is not None
                or outstanding_mutation_planning_prerequisites
                or follow_up_review_reference is not None
            )
            and not class_definition.allow_mutation_planning_prerequisite_deferral
        ):
            return True

        return False

    def _requires_mutation_planning_restrictions(
        self,
        policy_learning_update_preparation: PolicyLearningUpdatePreparationRecord,
        class_definition,
        combined_context: Mapping[str, object],
    ) -> bool:
        if not class_definition.allow_mutation_planning_restrictions:
            return False
        if (
            policy_learning_update_preparation.policy_learning_update_preparation_outcome
            == "prepared_with_restrictions"
        ):
            return True
        if self._optional_text(combined_context.get("restriction_summary")) is not None:
            return True
        if (
            self._optional_text(
                combined_context.get("mutation_scope_restriction_reference")
            )
            is not None
        ):
            return True
        return False

    def _requires_mutation_planning_prerequisite_deferral(
        self,
        class_definition,
        combined_context: Mapping[str, object],
    ) -> bool:
        if not class_definition.allow_mutation_planning_prerequisite_deferral:
            return False
        if (
            self._optional_text(
                combined_context.get("mutation_planning_prerequisite_reference")
            )
            is not None
        ):
            return True
        if self._sequence_as_tuple(
            combined_context.get("outstanding_mutation_planning_prerequisites")
        ):
            return True
        if (
            self._optional_text(combined_context.get("follow_up_review_reference"))
            is not None
        ):
            return True
        return False

    def _mutation_planning_outcome(
        self,
        *,
        template,
        mutation_planning_status: str,
    ) -> str:
        if mutation_planning_status in {
            "blocked_missing_context",
            "rejected_for_mutation_planning_use",
            "prohibited_overlap_blocked",
        }:
            return mutation_planning_status
        return template.policy_learning_update_mutation_planning_outcome

    def _reason(
        self,
        *,
        policy_learning_update_preparation: PolicyLearningUpdatePreparationRecord,
        mutation_planning_status: str,
        policy_learning_update_mutation_planning_class_id: str,
        missing_update_mutation_planning_fields: tuple[str, ...],
        prohibited_update_mutation_planning_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        mutation_planning_outcome: str,
    ) -> str:
        if mutation_planning_status == "blocked_missing_context":
            return (
                "Policy-learning update-mutation-planning review is missing required mutation-planning fields: "
                + ", ".join(missing_update_mutation_planning_fields)
                + "."
            )
        if mutation_planning_status == "prohibited_overlap_blocked":
            return (
                "Policy-learning update-mutation-planning class "
                f"'{policy_learning_update_mutation_planning_class_id}' cannot carry policy mutation, "
                "rollout, deployment, retraining, monitoring, reopen, orchestration, or lifecycle fields: "
                + ", ".join(prohibited_update_mutation_planning_fields_present)
                + "."
            )
        if mutation_planning_status == "rejected_for_mutation_planning_use":
            return (
                "Policy-learning update-mutation-planning class "
                f"'{policy_learning_update_mutation_planning_class_id}' rejected the preparation candidate "
                "because the upstream preparation posture or mutation-planning dimensions remain below the governed mutation-planning standard. "
                "Required minimums are preparation_status in "
                f"{class_definition.allowed_policy_learning_update_preparation_statuses}, preparation_outcome in "
                f"{class_definition.allowed_policy_learning_update_preparation_outcomes}, and mutation-planning-dimension-strength>="
                f"{class_definition.minimum_dimension_strength}. Current upstream status is "
                f"'{policy_learning_update_preparation.policy_learning_update_preparation_status}' with outcome "
                f"'{policy_learning_update_preparation.policy_learning_update_preparation_outcome}'."
            )
        if mutation_planning_outcome == "ready_for_policy_mutation_planning_with_restrictions":
            restriction_summary = self._optional_text(
                combined_context.get("restriction_summary")
            ) or "governed scope restrictions remain attached to mutation-planning"
            return (
                "Policy-learning update mutation planning is ready only with explicit restrictions because the prepared candidate remains locally narrowed or otherwise constraint-bound. "
                f"Restriction summary: {restriction_summary}."
            )
        if mutation_planning_outcome == "deferred_pending_mutation_planning_prerequisites":
            return (
                "Policy-learning update mutation planning is deferred pending explicit mutation-planning prerequisites because outstanding prerequisite items or follow-up review controls still prevent current mutation-plan formulation."
            )
        return (
            "Policy-learning update mutation planning is ready and the governed preparation candidate is bounded for downstream policy mutation execution planning while preserving separate ownership for actual mutation execution, rollout, deployment, retraining, monitoring, and lifecycle handling."
        )

    def _lineage(
        self,
        request: PolicyLearningUpdateMutationPlanningRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.policy_learning_update_preparation.lineage)
        lineage.update(
            {
                "policy_learning_update_preparation_id": (
                    request.policy_learning_update_preparation.policy_learning_update_preparation_id
                ),
                "policy_learning_update_mutation_planning_class_id": (
                    class_definition.policy_learning_update_mutation_planning_class_id
                ),
                "policy_learning_update_mutation_planning_class_version": (
                    class_definition.lineage.get("version", "unknown")
                ),
                "policy_learning_update_mutation_planning_template_id": (
                    template.policy_learning_update_mutation_planning_template_id
                ),
                "policy_learning_update_mutation_planning_template_version": (
                    template.lineage.get("version", "unknown")
                ),
            }
        )
        return lineage

    def _field_value_or_placeholder(
        self,
        *,
        field_name: str,
        snapshot: Mapping[str, str],
        context: Mapping[str, object],
    ) -> str:
        snapshot_value = snapshot.get(field_name)
        if snapshot_value is not None:
            return snapshot_value
        context_value = self._optional_text(context.get(field_name))
        if context_value is not None:
            return context_value
        return f"missing_{field_name}"

    def _dimension_strength_rank(self, dimension_strength: str) -> int:
        return _DIMENSION_STRENGTH_RANK.get(dimension_strength, -1)

    def _dimension_strength_rank_from_context(
        self,
        context: Mapping[str, object],
    ) -> int:
        return min(
            self._dimension_strength_rank(
                self._optional_text(context.get(field_name)) or ""
            )
            for field_name in _DIMENSION_FIELDS
        )

    def _optional_text(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text

    def _sequence_as_tuple(self, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (list, tuple)):
            return tuple(str(item) for item in value if str(item).strip())
        text = self._optional_text(value)
        if text is None:
            return ()
        return (text,)

    def _to_text(self, value: object) -> str:
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)

    def _is_missing_value(self, value: object) -> bool:
        return value is None or value == "" or value == () or value == []