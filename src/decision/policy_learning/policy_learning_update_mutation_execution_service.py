from __future__ import annotations

"""Governed policy-learning update mutation execution.

Canon ownership:
- Consumes a governed policy-learning update-mutation-planning record and
  explicit mutation-execution context to decide whether bounded policy
  mutation execution is ready, ready with restrictions, deferred, blocked for
  missing context, rejected for mutation-execution use, or blocked for
  prohibited overlap.
- Does not own rollout or deployment execution, retraining execution,
  model-update execution, drift monitoring, reopen handling, orchestration
  meaning, lifecycle state meaning, mutation-planning judgment, preparation
  judgment, approval judgment, evidence admission, threshold judgment, or
  execution outcome capture.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from decision.policy_learning.policy_learning_update_mutation_execution_audit_adapter import (
    PolicyLearningUpdateMutationExecutionAuditAdapter,
)
from decision.policy_learning.policy_learning_update_mutation_execution_registry import (
    PolicyLearningUpdateMutationExecutionRegistry,
)
from decision.policy_learning.policy_learning_update_mutation_planning_service import (
    PolicyLearningUpdateMutationPlanningRecord,
)

_DIMENSION_STRENGTH_RANK = {"weak": 0, "moderate": 1, "strong": 2}
_DIMENSION_FIELDS = (
    "mutation_readiness",
    "safeguard_readiness",
    "rollback_readiness",
    "execution_readiness",
    "verification_readiness",
    "rollback_execution_readiness",
)
_REQUIRED_COLLECTION_FIELDS = {
    "required_update_mutation_execution_fields",
    "optional_update_mutation_execution_fields",
    "required_audit_fields",
    "prohibited_update_mutation_execution_fields",
    "required_update_mutation_execution_snapshot",
    "optional_update_mutation_execution_snapshot",
    "required_audit_snapshot",
    "lineage",
}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value


def _serialize_payload(data: Mapping[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in data.items():
        if value is None:
            continue
        if key not in _REQUIRED_COLLECTION_FIELDS and value in ((), [], {}):
            continue
        payload[key] = _serialize_value(value)
    return payload


@dataclass(frozen=True)
class PolicyLearningUpdateMutationExecutionRequest:
    policy_learning_update_mutation_planning: PolicyLearningUpdateMutationPlanningRecord
    policy_learning_update_mutation_execution_class_id: str
    policy_learning_update_mutation_execution_author_role: str
    policy_learning_update_mutation_execution_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class PolicyLearningUpdateMutationExecutionRecord:
    policy_learning_update_mutation_execution_id: str
    policy_learning_update_mutation_execution_status: str
    reason: str
    policy_learning_update_mutation_execution_class_id: str
    policy_learning_update_mutation_execution_template_id: str
    policy_learning_update_mutation_execution_outcome: str
    mutation_readiness: str
    safeguard_readiness: str
    rollback_readiness: str
    execution_readiness: str
    verification_readiness: str
    rollback_execution_readiness: str
    mutation_plan_reference: str
    mutation_planning_summary: str
    mutation_plan_scope_reference: str
    mutation_planning_boundary_summary: str
    policy_mutation_payload: str
    policy_mutation_execution_reference: str
    mutated_policy_reference: str
    mutation_execution_summary: str
    mutation_execution_scope_reference: str
    mutation_execution_boundary_summary: str
    policy_learning_update_mutation_planning_id: str
    policy_learning_update_mutation_planning_status: str
    policy_learning_update_mutation_planning_class_id: str
    policy_learning_update_mutation_planning_template_id: str
    policy_learning_update_mutation_planning_outcome: str
    artifact_readiness: str
    planning_readiness: str
    prerequisite_readiness: str
    preparation_package_reference: str
    preparation_summary: str
    mutation_planning_scope_reference: str
    preparation_artifact_boundary_summary: str
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
    policy_learning_update_mutation_execution_author_role: str
    policy_learning_update_mutation_execution_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_update_mutation_execution_fields: tuple[str, ...]
    optional_update_mutation_execution_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_update_mutation_execution_fields: tuple[str, ...]
    required_update_mutation_execution_snapshot: Mapping[str, str]
    optional_update_mutation_execution_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    domain_reference: str | None = None
    decision_scope_reference: str | None = None
    reporting_scope_reference: str | None = None
    tenant_scope_reference: str | None = None
    learning_scope_reference: str | None = None
    restriction_summary: str | None = None
    mutation_execution_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    mutation_execution_prerequisite_reference: str | None = None
    outstanding_mutation_execution_prerequisites: tuple[str, ...] = ()
    missing_update_mutation_execution_fields: tuple[str, ...] = ()
    prohibited_update_mutation_execution_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        return _serialize_payload(asdict(self))

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "policy_learning_update_mutation_execution_outcome": (
                self.policy_learning_update_mutation_execution_outcome
            ),
            "policy_mutation_execution_reference": (
                self.policy_mutation_execution_reference
            ),
            "mutated_policy_reference": self.mutated_policy_reference,
        }
        if self.restriction_summary is not None:
            context["restriction_summary"] = self.restriction_summary
        if self.mutation_execution_scope_restriction_reference is not None:
            context["mutation_execution_scope_restriction_reference"] = (
                self.mutation_execution_scope_restriction_reference
            )
        if self.follow_up_review_reference is not None:
            context["follow_up_review_reference"] = self.follow_up_review_reference
        if self.mutation_execution_prerequisite_reference is not None:
            context["mutation_execution_prerequisite_reference"] = (
                self.mutation_execution_prerequisite_reference
            )
        if self.outstanding_mutation_execution_prerequisites:
            context["outstanding_mutation_execution_prerequisites"] = list(
                self.outstanding_mutation_execution_prerequisites
            )
        return context


class PolicyLearningUpdateMutationExecutionService:
    """Builds policy-learning update-mutation-execution records."""

    def __init__(
        self,
        *,
        policy_learning_update_mutation_execution_registry: PolicyLearningUpdateMutationExecutionRegistry,
        policy_learning_update_mutation_execution_audit_adapter: PolicyLearningUpdateMutationExecutionAuditAdapter,
    ) -> None:
        self._policy_learning_update_mutation_execution_registry = (
            policy_learning_update_mutation_execution_registry
        )
        self._policy_learning_update_mutation_execution_audit_adapter = (
            policy_learning_update_mutation_execution_audit_adapter
        )

    def generate(
        self,
        request: PolicyLearningUpdateMutationExecutionRequest,
    ) -> PolicyLearningUpdateMutationExecutionRecord:
        template, fallback_template_used = (
            self._policy_learning_update_mutation_execution_registry.resolve_template(
                semantic_scope=request.policy_learning_update_mutation_planning.semantic_scope,
                policy_learning_update_mutation_planning_class_id=(
                    request.policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id
                ),
                policy_learning_update_mutation_execution_class_id=(
                    request.policy_learning_update_mutation_execution_class_id
                ),
                route_name=request.policy_learning_update_mutation_planning.lineage.get(
                    "route_name"
                ),
            )
        )
        class_definition = self._policy_learning_update_mutation_execution_registry.get_policy_learning_update_mutation_execution_class(
            request.policy_learning_update_mutation_execution_class_id
        )
        combined_context = self._combined_context(request, class_definition)
        (
            required_update_mutation_execution_snapshot,
            missing_update_mutation_execution_fields,
        ) = self._snapshot_required_fields(
            template.required_update_mutation_execution_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_update_mutation_execution_fields + missing_audit_fields)
        )
        optional_update_mutation_execution_snapshot = self._snapshot_optional_fields(
            template.optional_update_mutation_execution_fields,
            combined_context,
        )
        prohibited_update_mutation_execution_fields_present = (
            self._prohibited_update_mutation_execution_fields_present(
                class_definition.prohibited_update_mutation_execution_fields,
                request.policy_learning_update_mutation_execution_context,
            )
        )
        mutation_execution_status = self._mutation_execution_status(
            policy_learning_update_mutation_planning=(
                request.policy_learning_update_mutation_planning
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            missing_update_mutation_execution_fields=all_missing_fields,
            prohibited_update_mutation_execution_fields_present=(
                prohibited_update_mutation_execution_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        mutation_execution_outcome = self._mutation_execution_outcome(
            template=template,
            mutation_execution_status=mutation_execution_status,
        )
        reason = self._reason(
            policy_learning_update_mutation_planning=(
                request.policy_learning_update_mutation_planning
            ),
            mutation_execution_status=mutation_execution_status,
            policy_learning_update_mutation_execution_class_id=(
                class_definition.policy_learning_update_mutation_execution_class_id
            ),
            missing_update_mutation_execution_fields=all_missing_fields,
            prohibited_update_mutation_execution_fields_present=(
                prohibited_update_mutation_execution_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            mutation_execution_outcome=mutation_execution_outcome,
        )
        lineage = self._lineage(request, class_definition, template)

        upstream = request.policy_learning_update_mutation_planning
        record = PolicyLearningUpdateMutationExecutionRecord(
            policy_learning_update_mutation_execution_id=str(uuid4()),
            policy_learning_update_mutation_execution_status=mutation_execution_status,
            reason=reason,
            policy_learning_update_mutation_execution_class_id=(
                class_definition.policy_learning_update_mutation_execution_class_id
            ),
            policy_learning_update_mutation_execution_template_id=(
                template.policy_learning_update_mutation_execution_template_id
            ),
            policy_learning_update_mutation_execution_outcome=mutation_execution_outcome,
            mutation_readiness=self._field_value_or_placeholder(
                field_name="mutation_readiness",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            safeguard_readiness=self._field_value_or_placeholder(
                field_name="safeguard_readiness",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            rollback_readiness=self._field_value_or_placeholder(
                field_name="rollback_readiness",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            execution_readiness=self._field_value_or_placeholder(
                field_name="execution_readiness",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            verification_readiness=self._field_value_or_placeholder(
                field_name="verification_readiness",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            rollback_execution_readiness=self._field_value_or_placeholder(
                field_name="rollback_execution_readiness",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            mutation_plan_reference=self._field_value_or_placeholder(
                field_name="mutation_plan_reference",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            mutation_planning_summary=self._field_value_or_placeholder(
                field_name="mutation_planning_summary",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            mutation_plan_scope_reference=self._field_value_or_placeholder(
                field_name="mutation_plan_scope_reference",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            mutation_planning_boundary_summary=self._field_value_or_placeholder(
                field_name="mutation_planning_boundary_summary",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            policy_mutation_payload=self._field_value_or_placeholder(
                field_name="policy_mutation_payload",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            policy_mutation_execution_reference=self._field_value_or_placeholder(
                field_name="policy_mutation_execution_reference",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            mutated_policy_reference=self._field_value_or_placeholder(
                field_name="mutated_policy_reference",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            mutation_execution_summary=self._field_value_or_placeholder(
                field_name="mutation_execution_summary",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            mutation_execution_scope_reference=self._field_value_or_placeholder(
                field_name="mutation_execution_scope_reference",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            mutation_execution_boundary_summary=self._field_value_or_placeholder(
                field_name="mutation_execution_boundary_summary",
                snapshot=required_update_mutation_execution_snapshot,
                context=combined_context,
            ),
            policy_learning_update_mutation_planning_id=(
                upstream.policy_learning_update_mutation_planning_id
            ),
            policy_learning_update_mutation_planning_status=(
                upstream.policy_learning_update_mutation_planning_status
            ),
            policy_learning_update_mutation_planning_class_id=(
                upstream.policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_template_id=(
                upstream.policy_learning_update_mutation_planning_template_id
            ),
            policy_learning_update_mutation_planning_outcome=(
                upstream.policy_learning_update_mutation_planning_outcome
            ),
            artifact_readiness=upstream.artifact_readiness,
            planning_readiness=upstream.planning_readiness,
            prerequisite_readiness=upstream.prerequisite_readiness,
            preparation_package_reference=upstream.preparation_package_reference,
            preparation_summary=upstream.preparation_summary,
            mutation_planning_scope_reference=upstream.mutation_planning_scope_reference,
            preparation_artifact_boundary_summary=(
                upstream.preparation_artifact_boundary_summary
            ),
            policy_learning_update_preparation_id=(
                upstream.policy_learning_update_preparation_id
            ),
            policy_learning_update_preparation_status=(
                upstream.policy_learning_update_preparation_status
            ),
            policy_learning_update_preparation_class_id=(
                upstream.policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_template_id=(
                upstream.policy_learning_update_preparation_template_id
            ),
            policy_learning_update_preparation_outcome=(
                upstream.policy_learning_update_preparation_outcome
            ),
            policy_learning_update_approval_id=upstream.policy_learning_update_approval_id,
            policy_learning_update_approval_status=(
                upstream.policy_learning_update_approval_status
            ),
            policy_learning_update_approval_class_id=(
                upstream.policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_template_id=(
                upstream.policy_learning_update_approval_template_id
            ),
            policy_learning_update_approval_outcome=(
                upstream.policy_learning_update_approval_outcome
            ),
            governance_readiness=upstream.governance_readiness,
            change_control_readiness=upstream.change_control_readiness,
            boundary_control_strength=upstream.boundary_control_strength,
            preparation_readiness=upstream.preparation_readiness,
            candidate_update_reference=upstream.candidate_update_reference,
            approval_summary=upstream.approval_summary,
            change_control_reference=upstream.change_control_reference,
            preparation_scope_reference=upstream.preparation_scope_reference,
            preparation_boundary_summary=upstream.preparation_boundary_summary,
            policy_learning_update_threshold_id=(
                upstream.policy_learning_update_threshold_id
            ),
            policy_learning_update_threshold_status=(
                upstream.policy_learning_update_threshold_status
            ),
            policy_learning_update_threshold_class_id=(
                upstream.policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_template_id=(
                upstream.policy_learning_update_threshold_template_id
            ),
            policy_learning_update_decision_outcome=(
                upstream.policy_learning_update_decision_outcome
            ),
            evidence_sufficiency=upstream.evidence_sufficiency,
            weak_evidence_check=upstream.weak_evidence_check,
            policy_behavior_change=upstream.policy_behavior_change,
            update_severity=upstream.update_severity,
            update_scope=upstream.update_scope,
            policy_learning_evidence_admission_id=(
                upstream.policy_learning_evidence_admission_id
            ),
            policy_learning_evidence_admission_status=(
                upstream.policy_learning_evidence_admission_status
            ),
            policy_learning_evidence_class_id=(
                upstream.policy_learning_evidence_class_id
            ),
            policy_learning_evidence_template_id=(
                upstream.policy_learning_evidence_template_id
            ),
            policy_learning_evidence_admission_outcome=(
                upstream.policy_learning_evidence_admission_outcome
            ),
            post_mortem_judgment_id=upstream.post_mortem_judgment_id,
            post_mortem_judgment_status=upstream.post_mortem_judgment_status,
            post_mortem_judgment_class_id=upstream.post_mortem_judgment_class_id,
            post_mortem_judgment_template_id=(
                upstream.post_mortem_judgment_template_id
            ),
            execution_outcome_id=upstream.execution_outcome_id,
            execution_outcome_status=upstream.execution_outcome_status,
            execution_outcome_class_id=upstream.execution_outcome_class_id,
            execution_dispatch_id=upstream.execution_dispatch_id,
            execution_dispatch_class_id=upstream.execution_dispatch_class_id,
            execution_request_id=upstream.execution_request_id,
            semantic_scope=upstream.semantic_scope,
            case_type=upstream.case_type,
            case_key=upstream.case_key,
            state_model_name=upstream.state_model_name,
            episode_id=upstream.episode_id,
            transition_name=upstream.transition_name,
            transition_class=upstream.transition_class,
            source_stage=upstream.source_stage,
            target_stage=upstream.target_stage,
            policy_learning_update_threshold_author_role=(
                upstream.policy_learning_update_threshold_author_role
            ),
            policy_learning_update_threshold_author_id=(
                upstream.policy_learning_update_threshold_author_id
            ),
            policy_learning_update_approval_author_role=(
                upstream.policy_learning_update_approval_author_role
            ),
            policy_learning_update_approval_author_id=(
                upstream.policy_learning_update_approval_author_id
            ),
            policy_learning_update_preparation_author_role=(
                upstream.policy_learning_update_preparation_author_role
            ),
            policy_learning_update_preparation_author_id=(
                upstream.policy_learning_update_preparation_author_id
            ),
            policy_learning_update_mutation_planning_author_role=(
                upstream.policy_learning_update_mutation_planning_author_role
            ),
            policy_learning_update_mutation_planning_author_id=(
                upstream.policy_learning_update_mutation_planning_author_id
            ),
            policy_learning_update_mutation_execution_author_role=(
                request.policy_learning_update_mutation_execution_author_role
            ),
            policy_learning_update_mutation_execution_author_id=request.actor_id,
            authority_resolution_kind=upstream.authority_resolution_kind,
            authority_review_required=upstream.authority_review_required,
            router_rule_id=upstream.router_rule_id,
            routing_resolution_status=upstream.routing_resolution_status,
            routing_review_required=upstream.routing_review_required,
            review_mode=upstream.review_mode,
            required_update_mutation_execution_fields=(
                template.required_update_mutation_execution_fields
            ),
            optional_update_mutation_execution_fields=(
                template.optional_update_mutation_execution_fields
            ),
            required_audit_fields=template.required_audit_fields,
            prohibited_update_mutation_execution_fields=(
                class_definition.prohibited_update_mutation_execution_fields
            ),
            required_update_mutation_execution_snapshot=(
                required_update_mutation_execution_snapshot
            ),
            optional_update_mutation_execution_snapshot=(
                optional_update_mutation_execution_snapshot
            ),
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
            mutation_execution_scope_restriction_reference=self._optional_text(
                combined_context.get("mutation_execution_scope_restriction_reference")
            ),
            follow_up_review_reference=self._optional_text(
                combined_context.get("follow_up_review_reference")
            ),
            mutation_execution_prerequisite_reference=self._optional_text(
                combined_context.get("mutation_execution_prerequisite_reference")
            ),
            outstanding_mutation_execution_prerequisites=self._sequence_as_tuple(
                combined_context.get("outstanding_mutation_execution_prerequisites")
            ),
            missing_update_mutation_execution_fields=all_missing_fields,
            prohibited_update_mutation_execution_fields_present=(
                prohibited_update_mutation_execution_fields_present
            ),
        )
        self._policy_learning_update_mutation_execution_audit_adapter.record_policy_learning_update_mutation_execution(
            record,
            request=request,
        )
        return record

    def _combined_context(
        self,
        request: PolicyLearningUpdateMutationExecutionRequest,
        class_definition,
    ) -> dict[str, object]:
        context = dict(
            request.policy_learning_update_mutation_planning.required_update_mutation_planning_snapshot
        )
        context.update(
            request.policy_learning_update_mutation_planning.optional_update_mutation_planning_snapshot
        )
        context.update(request.policy_learning_update_mutation_planning.required_audit_snapshot)
        context.update(dict(request.policy_learning_update_mutation_execution_context))
        upstream = request.policy_learning_update_mutation_planning
        context.update(
            {
                "policy_learning_update_mutation_execution_class_id": (
                    class_definition.policy_learning_update_mutation_execution_class_id
                ),
                "policy_learning_update_mutation_execution_author_id": request.actor_id,
                "policy_learning_update_mutation_execution_author_role": (
                    request.policy_learning_update_mutation_execution_author_role
                ),
                "policy_learning_update_mutation_planning_id": (
                    upstream.policy_learning_update_mutation_planning_id
                ),
                "policy_learning_update_mutation_planning_status": (
                    upstream.policy_learning_update_mutation_planning_status
                ),
                "policy_learning_update_mutation_planning_class_id": (
                    upstream.policy_learning_update_mutation_planning_class_id
                ),
                "policy_learning_update_mutation_planning_template_id": (
                    upstream.policy_learning_update_mutation_planning_template_id
                ),
                "policy_learning_update_mutation_planning_outcome": (
                    upstream.policy_learning_update_mutation_planning_outcome
                ),
                "artifact_readiness": upstream.artifact_readiness,
                "planning_readiness": upstream.planning_readiness,
                "prerequisite_readiness": upstream.prerequisite_readiness,
                "mutation_readiness": upstream.mutation_readiness,
                "safeguard_readiness": upstream.safeguard_readiness,
                "rollback_readiness": upstream.rollback_readiness,
                "mutation_plan_reference": upstream.mutation_plan_reference,
                "mutation_planning_summary": upstream.mutation_planning_summary,
                "mutation_plan_scope_reference": upstream.mutation_plan_scope_reference,
                "mutation_planning_boundary_summary": (
                    upstream.mutation_planning_boundary_summary
                ),
                "domain_reference": self._optional_text(context.get("domain_reference"))
                or upstream.domain_reference
                or upstream.semantic_scope,
                "decision_scope_reference": self._optional_text(
                    context.get("decision_scope_reference")
                )
                or upstream.decision_scope_reference
                or "",
                "reporting_scope_reference": self._optional_text(
                    context.get("reporting_scope_reference")
                )
                or upstream.reporting_scope_reference
                or "",
                "tenant_scope_reference": self._optional_text(
                    context.get("tenant_scope_reference")
                )
                or upstream.tenant_scope_reference
                or "",
                "learning_scope_reference": self._optional_text(
                    context.get("learning_scope_reference")
                )
                or upstream.learning_scope_reference
                or upstream.update_scope,
                "candidate_update_reference": self._optional_text(
                    context.get("candidate_update_reference")
                )
                or upstream.candidate_update_reference,
                "restriction_summary": self._optional_text(
                    context.get("restriction_summary")
                )
                or upstream.restriction_summary,
                "follow_up_review_reference": self._optional_text(
                    context.get("follow_up_review_reference")
                )
                or upstream.follow_up_review_reference,
                "mutation_execution_scope_reference": self._optional_text(
                    context.get("mutation_execution_scope_reference")
                )
                or upstream.mutation_plan_scope_reference
                or upstream.mutation_planning_scope_reference,
                "mutation_execution_scope_restriction_reference": self._optional_text(
                    context.get("mutation_execution_scope_restriction_reference")
                )
                or upstream.mutation_scope_restriction_reference,
                "mutation_execution_prerequisite_reference": self._optional_text(
                    context.get("mutation_execution_prerequisite_reference")
                )
                or upstream.mutation_planning_prerequisite_reference,
                "outstanding_mutation_execution_prerequisites": (
                    self._sequence_as_tuple(
                        context.get("outstanding_mutation_execution_prerequisites")
                    )
                    or upstream.outstanding_mutation_planning_prerequisites
                ),
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

    def _prohibited_update_mutation_execution_fields_present(
        self,
        prohibited_fields: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in prohibited_fields
            if not self._is_missing_value(context.get(field_name))
        )

    def _mutation_execution_status(
        self,
        *,
        policy_learning_update_mutation_planning: PolicyLearningUpdateMutationPlanningRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_update_mutation_execution_fields: tuple[str, ...],
        prohibited_update_mutation_execution_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_update_mutation_execution_fields_present:
            return "prohibited_overlap_blocked"
        if missing_update_mutation_execution_fields:
            return "blocked_missing_context"
        if (
            policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_status
            not in class_definition.allowed_policy_learning_update_mutation_planning_statuses
        ):
            return "rejected_for_mutation_execution_use"
        if (
            policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_outcome
            not in class_definition.allowed_policy_learning_update_mutation_planning_outcomes
        ):
            return "rejected_for_mutation_execution_use"
        if self._dimension_strength_rank_from_context(combined_context) < self._minimum_rank(
            class_definition.minimum_dimension_strength
        ):
            return "rejected_for_mutation_execution_use"
        if (
            self._has_execution_restrictions(combined_context)
            and not class_definition.allow_mutation_execution_restrictions
        ):
            return "rejected_for_mutation_execution_use"
        if (
            self._has_execution_prerequisite_deferral(combined_context)
            and not class_definition.allow_mutation_execution_prerequisite_deferral
        ):
            return "rejected_for_mutation_execution_use"
        return "fallback_template_applied" if fallback_template_used else "mutation_execution_ready"

    def _mutation_execution_outcome(
        self,
        *,
        template,
        mutation_execution_status: str,
    ) -> str:
        if mutation_execution_status in {
            "blocked_missing_context",
            "rejected_for_mutation_execution_use",
            "prohibited_overlap_blocked",
        }:
            return mutation_execution_status
        return template.policy_learning_update_mutation_execution_outcome

    def _reason(
        self,
        *,
        policy_learning_update_mutation_planning: PolicyLearningUpdateMutationPlanningRecord,
        mutation_execution_status: str,
        policy_learning_update_mutation_execution_class_id: str,
        missing_update_mutation_execution_fields: tuple[str, ...],
        prohibited_update_mutation_execution_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        mutation_execution_outcome: str,
    ) -> str:
        if mutation_execution_status == "blocked_missing_context":
            return (
                "Policy-learning update mutation execution is blocked because governed "
                "mutation-execution context is missing required fields: "
                + ", ".join(missing_update_mutation_execution_fields)
                + "."
            )
        if mutation_execution_status == "prohibited_overlap_blocked":
            return (
                "Policy-learning update mutation execution is blocked because context "
                "overlaps rollout, deployment, retraining, model-update, monitoring, "
                "reopen, or orchestration fields: "
                + ", ".join(prohibited_update_mutation_execution_fields_present)
                + "."
            )
        if mutation_execution_status == "rejected_for_mutation_execution_use":
            if (
                policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_status
                not in class_definition.allowed_policy_learning_update_mutation_planning_statuses
            ):
                return (
                    "Policy-learning update mutation execution rejects mutation-planning "
                    "status '"
                    f"{policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_status}' "
                    "for class '"
                    f"{policy_learning_update_mutation_execution_class_id}'."
                )
            if (
                policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_outcome
                not in class_definition.allowed_policy_learning_update_mutation_planning_outcomes
            ):
                return (
                    "Policy-learning update mutation execution rejects mutation-planning "
                    "outcome '"
                    f"{policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_outcome}' "
                    "for class '"
                    f"{policy_learning_update_mutation_execution_class_id}'."
                )
            if self._has_execution_restrictions(combined_context) and not (
                class_definition.allow_mutation_execution_restrictions
            ):
                return (
                    "Policy-learning update mutation execution rejects restricted "
                    "execution context for class '"
                    f"{policy_learning_update_mutation_execution_class_id}'."
                )
            if self._has_execution_prerequisite_deferral(combined_context) and not (
                class_definition.allow_mutation_execution_prerequisite_deferral
            ):
                return (
                    "Policy-learning update mutation execution rejects deferred "
                    "execution prerequisites for class '"
                    f"{policy_learning_update_mutation_execution_class_id}'."
                )
            return (
                "Policy-learning update mutation execution rejects this mutation plan "
                "because execution readiness is below the class minimum."
            )
        if mutation_execution_outcome == "ready_for_policy_mutation_execution":
            return "Governed policy mutation execution is ready within the bounded execution scope."
        if (
            mutation_execution_outcome
            == "ready_for_policy_mutation_execution_with_restrictions"
        ):
            return (
                "Governed policy mutation execution is ready with explicit execution "
                "restrictions preserved."
            )
        return (
            "Governed policy mutation execution is deferred until explicit mutation-"
            "execution prerequisites are completed."
        )

    def _lineage(
        self,
        request: PolicyLearningUpdateMutationExecutionRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.policy_learning_update_mutation_planning.lineage)
        lineage.update(
            {
                "policy_learning_update_mutation_planning_id": (
                    request.policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_id
                ),
                "policy_learning_update_mutation_execution_class_id": (
                    class_definition.policy_learning_update_mutation_execution_class_id
                ),
                "policy_learning_update_mutation_execution_template_id": (
                    template.policy_learning_update_mutation_execution_template_id
                ),
            }
        )
        return lineage

    def _dimension_strength_rank_from_context(
        self,
        context: Mapping[str, object],
    ) -> int:
        ranks: list[int] = []
        for field_name in _DIMENSION_FIELDS:
            value = self._optional_text(context.get(field_name))
            if value not in _DIMENSION_STRENGTH_RANK:
                return -1
            ranks.append(_DIMENSION_STRENGTH_RANK[value])
        return min(ranks) if ranks else -1

    def _minimum_rank(self, minimum_dimension_strength: str) -> int:
        return _DIMENSION_STRENGTH_RANK[minimum_dimension_strength]

    def _has_execution_restrictions(self, context: Mapping[str, object]) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "restriction_summary",
                "mutation_execution_scope_restriction_reference",
            )
        )

    def _has_execution_prerequisite_deferral(
        self,
        context: Mapping[str, object],
    ) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "mutation_execution_prerequisite_reference",
                "outstanding_mutation_execution_prerequisites",
            )
        )

    def _field_value_or_placeholder(
        self,
        *,
        field_name: str,
        snapshot: Mapping[str, str],
        context: Mapping[str, object],
    ) -> str:
        if field_name in snapshot:
            return snapshot[field_name]
        return self._to_text(context.get(field_name, ""))

    def _optional_text(self, value: object) -> str | None:
        if self._is_missing_value(value):
            return None
        return self._to_text(value)

    def _sequence_as_tuple(self, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, tuple):
            return tuple(self._to_text(item) for item in value if not self._is_missing_value(item))
        if isinstance(value, list):
            return tuple(self._to_text(item) for item in value if not self._is_missing_value(item))
        return (self._to_text(value),)

    def _is_missing_value(self, value: object) -> bool:
        return value is None or value == "" or value == () or value == []

    def _to_text(self, value: object) -> str:
        if isinstance(value, str):
            return value
        return str(value)
