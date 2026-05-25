from __future__ import annotations

"""Governed policy-learning update approval.

Canon ownership:
- Consumes a governed policy-learning update-threshold record and explicit
  approval context to decide whether update preparation is approved,
  approved with restrictions, deferred, blocked for missing context,
  rejected for policy-update use, or blocked for prohibited overlap.
- Does not own actual policy mutation, rollout or deployment,
  retraining, monitoring, reopen handling, orchestration meaning,
  lifecycle state meaning, evidence admission, or threshold judgment.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping
from uuid import uuid4

from decision.policy_learning.policy_learning_update_approval_audit_adapter import (
    PolicyLearningUpdateApprovalAuditAdapter,
)
from decision.policy_learning.policy_learning_update_approval_registry import (
    PolicyLearningUpdateApprovalRegistry,
)
from decision.policy_learning.policy_learning_update_threshold_service import (
    PolicyLearningUpdateThresholdRecord,
)

_BLOCKED_OUTCOME = "rejected_for_policy_update_use"
_THRESHOLD_EVIDENCE_SUFFICIENCY_RANK = {
    "threshold_evidence_incomplete": 0,
    "threshold_evidence_overlap_prohibited": 0,
    "insufficient_for_update_threshold": 1,
    "insufficient_pending_more_evidence": 2,
    "sufficient_only_for_narrowed_scope": 3,
    "sufficient_for_proposed_update": 4,
}
_THRESHOLD_WEAK_EVIDENCE_CHECK_RANK = {
    "weak_evidence_check_failed": 0,
    "weak_evidence_check_blocked_for_overlap": 0,
    "weak_evidence_check_requires_monitoring": 1,
    "weak_evidence_check_requires_narrowing": 2,
    "weak_evidence_check_passed": 3,
}
_DIMENSION_STRENGTH_RANK = {"weak": 0, "moderate": 1, "strong": 2}
_DIMENSION_FIELDS = (
    "governance_readiness",
    "change_control_readiness",
    "boundary_control_strength",
    "preparation_readiness",
)


@dataclass(frozen=True)
class PolicyLearningUpdateApprovalRequest:
    policy_learning_update_threshold: PolicyLearningUpdateThresholdRecord
    policy_learning_update_approval_class_id: str
    policy_learning_update_approval_author_role: str
    policy_learning_update_approval_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class PolicyLearningUpdateApprovalRecord:
    policy_learning_update_approval_id: str
    policy_learning_update_approval_status: str
    reason: str
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
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_update_approval_fields: tuple[str, ...]
    optional_update_approval_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_update_approval_fields: tuple[str, ...]
    required_update_approval_snapshot: Mapping[str, str]
    optional_update_approval_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    domain_reference: str | None = None
    decision_scope_reference: str | None = None
    reporting_scope_reference: str | None = None
    tenant_scope_reference: str | None = None
    learning_scope_reference: str | None = None
    restriction_summary: str | None = None
    preparation_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    additional_governance_requirements: tuple[str, ...] = ()
    unresolved_governance_gaps: tuple[str, ...] = ()
    missing_update_approval_fields: tuple[str, ...] = ()
    prohibited_update_approval_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "policy_learning_update_approval_id": self.policy_learning_update_approval_id,
            "policy_learning_update_approval_status": self.policy_learning_update_approval_status,
            "reason": self.reason,
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
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "required_update_approval_fields": list(self.required_update_approval_fields),
            "optional_update_approval_fields": list(self.optional_update_approval_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_update_approval_fields": list(self.prohibited_update_approval_fields),
            "required_update_approval_snapshot": dict(self.required_update_approval_snapshot),
            "optional_update_approval_snapshot": dict(self.optional_update_approval_snapshot),
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
        if self.preparation_scope_restriction_reference is not None:
            payload["preparation_scope_restriction_reference"] = (
                self.preparation_scope_restriction_reference
            )
        if self.follow_up_review_reference is not None:
            payload["follow_up_review_reference"] = self.follow_up_review_reference
        if self.additional_governance_requirements:
            payload["additional_governance_requirements"] = list(
                self.additional_governance_requirements
            )
        if self.unresolved_governance_gaps:
            payload["unresolved_governance_gaps"] = list(
                self.unresolved_governance_gaps
            )
        if self.missing_update_approval_fields:
            payload["missing_update_approval_fields"] = list(
                self.missing_update_approval_fields
            )
        if self.prohibited_update_approval_fields_present:
            payload["prohibited_update_approval_fields_present"] = list(
                self.prohibited_update_approval_fields_present
            )
        return payload

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "policy_learning_update_approval_outcome": (
                self.policy_learning_update_approval_outcome
            ),
            "candidate_update_reference": self.candidate_update_reference,
        }
        if self.restriction_summary is not None:
            context["restriction_summary"] = self.restriction_summary
        if self.preparation_scope_restriction_reference is not None:
            context["preparation_scope_restriction_reference"] = (
                self.preparation_scope_restriction_reference
            )
        if self.follow_up_review_reference is not None:
            context["follow_up_review_reference"] = self.follow_up_review_reference
        if self.additional_governance_requirements:
            context["additional_governance_requirements"] = list(
                self.additional_governance_requirements
            )
        if self.unresolved_governance_gaps:
            context["unresolved_governance_gaps"] = list(
                self.unresolved_governance_gaps
            )
        return context


class PolicyLearningUpdateApprovalService:
    """Builds policy-learning update-approval records from threshold records."""

    def __init__(
        self,
        *,
        policy_learning_update_approval_registry: PolicyLearningUpdateApprovalRegistry,
        policy_learning_update_approval_audit_adapter: PolicyLearningUpdateApprovalAuditAdapter,
    ) -> None:
        self._policy_learning_update_approval_registry = (
            policy_learning_update_approval_registry
        )
        self._policy_learning_update_approval_audit_adapter = (
            policy_learning_update_approval_audit_adapter
        )

    def generate(
        self,
        request: PolicyLearningUpdateApprovalRequest,
    ) -> PolicyLearningUpdateApprovalRecord:
        template, fallback_template_used = (
            self._policy_learning_update_approval_registry.resolve_template(
                semantic_scope=request.policy_learning_update_threshold.semantic_scope,
                policy_learning_update_threshold_class_id=(
                    request.policy_learning_update_threshold.policy_learning_update_threshold_class_id
                ),
                policy_learning_update_approval_class_id=(
                    request.policy_learning_update_approval_class_id
                ),
                route_name=request.policy_learning_update_threshold.lineage.get(
                    "route_name"
                ),
            )
        )
        class_definition = (
            self._policy_learning_update_approval_registry.get_policy_learning_update_approval_class(
                request.policy_learning_update_approval_class_id
            )
        )
        combined_context = self._combined_context(request, class_definition)
        required_update_approval_snapshot, missing_update_approval_fields = (
            self._snapshot_required_fields(
                template.required_update_approval_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_update_approval_fields + missing_audit_fields)
        )
        optional_update_approval_snapshot = self._snapshot_optional_fields(
            template.optional_update_approval_fields,
            combined_context,
        )
        prohibited_update_approval_fields_present = (
            self._prohibited_update_approval_fields_present(
                class_definition.prohibited_update_approval_fields,
                request.policy_learning_update_approval_context,
            )
        )
        approval_status = self._approval_status(
            policy_learning_update_threshold=request.policy_learning_update_threshold,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_update_approval_fields=all_missing_fields,
            prohibited_update_approval_fields_present=(
                prohibited_update_approval_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        approval_outcome = self._approval_outcome(
            template=template,
            approval_status=approval_status,
        )
        reason = self._reason(
            policy_learning_update_threshold=request.policy_learning_update_threshold,
            approval_status=approval_status,
            policy_learning_update_approval_class_id=(
                class_definition.policy_learning_update_approval_class_id
            ),
            missing_update_approval_fields=all_missing_fields,
            prohibited_update_approval_fields_present=(
                prohibited_update_approval_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            approval_outcome=approval_outcome,
        )
        lineage = self._lineage(request, class_definition, template)

        policy_learning_update_approval = PolicyLearningUpdateApprovalRecord(
            policy_learning_update_approval_id=str(uuid4()),
            policy_learning_update_approval_status=approval_status,
            reason=reason,
            policy_learning_update_approval_class_id=(
                class_definition.policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_template_id=(
                template.policy_learning_update_approval_template_id
            ),
            policy_learning_update_approval_outcome=approval_outcome,
            governance_readiness=self._field_value_or_placeholder(
                field_name="governance_readiness",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            change_control_readiness=self._field_value_or_placeholder(
                field_name="change_control_readiness",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            boundary_control_strength=self._field_value_or_placeholder(
                field_name="boundary_control_strength",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            preparation_readiness=self._field_value_or_placeholder(
                field_name="preparation_readiness",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            candidate_update_reference=self._field_value_or_placeholder(
                field_name="candidate_update_reference",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            approval_summary=self._field_value_or_placeholder(
                field_name="approval_summary",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            change_control_reference=self._field_value_or_placeholder(
                field_name="change_control_reference",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            preparation_scope_reference=self._field_value_or_placeholder(
                field_name="preparation_scope_reference",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            preparation_boundary_summary=self._field_value_or_placeholder(
                field_name="preparation_boundary_summary",
                snapshot=required_update_approval_snapshot,
                context=combined_context,
            ),
            policy_learning_update_threshold_id=(
                request.policy_learning_update_threshold.policy_learning_update_threshold_id
            ),
            policy_learning_update_threshold_status=(
                request.policy_learning_update_threshold.policy_learning_update_threshold_status
            ),
            policy_learning_update_threshold_class_id=(
                request.policy_learning_update_threshold.policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_template_id=(
                request.policy_learning_update_threshold.policy_learning_update_threshold_template_id
            ),
            policy_learning_update_decision_outcome=(
                request.policy_learning_update_threshold.policy_learning_update_decision_outcome
            ),
            evidence_sufficiency=request.policy_learning_update_threshold.evidence_sufficiency,
            weak_evidence_check=request.policy_learning_update_threshold.weak_evidence_check,
            policy_behavior_change=(
                request.policy_learning_update_threshold.policy_behavior_change
            ),
            update_severity=request.policy_learning_update_threshold.update_severity,
            update_scope=request.policy_learning_update_threshold.update_scope,
            policy_learning_evidence_admission_id=(
                request.policy_learning_update_threshold.policy_learning_evidence_admission_id
            ),
            policy_learning_evidence_admission_status=(
                request.policy_learning_update_threshold.policy_learning_evidence_admission_status
            ),
            policy_learning_evidence_class_id=(
                request.policy_learning_update_threshold.policy_learning_evidence_class_id
            ),
            policy_learning_evidence_template_id=(
                request.policy_learning_update_threshold.policy_learning_evidence_template_id
            ),
            policy_learning_evidence_admission_outcome=(
                request.policy_learning_update_threshold.policy_learning_evidence_admission_outcome
            ),
            post_mortem_judgment_id=(
                request.policy_learning_update_threshold.post_mortem_judgment_id
            ),
            post_mortem_judgment_status=(
                request.policy_learning_update_threshold.post_mortem_judgment_status
            ),
            post_mortem_judgment_class_id=(
                request.policy_learning_update_threshold.post_mortem_judgment_class_id
            ),
            post_mortem_judgment_template_id=(
                request.policy_learning_update_threshold.post_mortem_judgment_template_id
            ),
            execution_outcome_id=request.policy_learning_update_threshold.execution_outcome_id,
            execution_outcome_status=(
                request.policy_learning_update_threshold.execution_outcome_status
            ),
            execution_outcome_class_id=(
                request.policy_learning_update_threshold.execution_outcome_class_id
            ),
            execution_dispatch_id=(
                request.policy_learning_update_threshold.execution_dispatch_id
            ),
            execution_dispatch_class_id=(
                request.policy_learning_update_threshold.execution_dispatch_class_id
            ),
            execution_request_id=request.policy_learning_update_threshold.execution_request_id,
            semantic_scope=request.policy_learning_update_threshold.semantic_scope,
            case_type=request.policy_learning_update_threshold.case_type,
            case_key=request.policy_learning_update_threshold.case_key,
            state_model_name=request.policy_learning_update_threshold.state_model_name,
            episode_id=request.policy_learning_update_threshold.episode_id,
            transition_name=request.policy_learning_update_threshold.transition_name,
            transition_class=request.policy_learning_update_threshold.transition_class,
            source_stage=request.policy_learning_update_threshold.source_stage,
            target_stage=request.policy_learning_update_threshold.target_stage,
            policy_learning_update_threshold_author_role=(
                request.policy_learning_update_threshold.policy_learning_update_threshold_author_role
            ),
            policy_learning_update_threshold_author_id=(
                request.policy_learning_update_threshold.policy_learning_update_threshold_author_id
            ),
            policy_learning_update_approval_author_role=(
                request.policy_learning_update_approval_author_role
            ),
            policy_learning_update_approval_author_id=request.actor_id,
            authority_resolution_kind=(
                request.policy_learning_update_threshold.authority_resolution_kind
            ),
            authority_review_required=(
                request.policy_learning_update_threshold.authority_review_required
            ),
            router_rule_id=request.policy_learning_update_threshold.router_rule_id,
            routing_resolution_status=(
                request.policy_learning_update_threshold.routing_resolution_status
            ),
            routing_review_required=(
                request.policy_learning_update_threshold.routing_review_required
            ),
            review_mode=request.policy_learning_update_threshold.review_mode,
            required_update_approval_fields=(
                template.required_update_approval_fields
            ),
            optional_update_approval_fields=(
                template.optional_update_approval_fields
            ),
            required_audit_fields=template.required_audit_fields,
            prohibited_update_approval_fields=(
                class_definition.prohibited_update_approval_fields
            ),
            required_update_approval_snapshot=required_update_approval_snapshot,
            optional_update_approval_snapshot=optional_update_approval_snapshot,
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
            preparation_scope_restriction_reference=self._optional_text(
                combined_context.get("preparation_scope_restriction_reference")
            ),
            follow_up_review_reference=self._optional_text(
                combined_context.get("follow_up_review_reference")
            ),
            additional_governance_requirements=self._sequence_as_tuple(
                combined_context.get("additional_governance_requirements")
            ),
            unresolved_governance_gaps=self._sequence_as_tuple(
                combined_context.get("unresolved_governance_gaps")
            ),
            missing_update_approval_fields=all_missing_fields,
            prohibited_update_approval_fields_present=(
                prohibited_update_approval_fields_present
            ),
        )
        self._policy_learning_update_approval_audit_adapter.record_policy_learning_update_approval(
            policy_learning_update_approval,
            request=request,
        )
        return policy_learning_update_approval

    def _combined_context(
        self,
        request: PolicyLearningUpdateApprovalRequest,
        class_definition,
    ) -> dict[str, object]:
        context = dict(
            request.policy_learning_update_threshold.required_update_threshold_snapshot
        )
        context.update(
            request.policy_learning_update_threshold.optional_update_threshold_snapshot
        )
        context.update(request.policy_learning_update_threshold.required_audit_snapshot)
        context.update(dict(request.policy_learning_update_approval_context))
        context.update(
            {
                "policy_learning_update_approval_class_id": (
                    class_definition.policy_learning_update_approval_class_id
                ),
                "policy_learning_update_approval_author_id": request.actor_id,
                "policy_learning_update_approval_author_role": (
                    request.policy_learning_update_approval_author_role
                ),
                "domain_reference": self._optional_text(context.get("domain_reference"))
                or request.policy_learning_update_threshold.domain_reference
                or request.policy_learning_update_threshold.semantic_scope,
                "decision_scope_reference": self._optional_text(
                    context.get("decision_scope_reference")
                )
                or request.policy_learning_update_threshold.decision_scope_reference
                or "",
                "reporting_scope_reference": self._optional_text(
                    context.get("reporting_scope_reference")
                )
                or request.policy_learning_update_threshold.reporting_scope_reference
                or "",
                "tenant_scope_reference": self._optional_text(
                    context.get("tenant_scope_reference")
                )
                or request.policy_learning_update_threshold.tenant_scope_reference
                or "",
                "learning_scope_reference": self._optional_text(
                    context.get("learning_scope_reference")
                )
                or request.policy_learning_update_threshold.learning_scope_reference
                or request.policy_learning_update_threshold.update_scope,
                "preparation_scope_reference": self._optional_text(
                    context.get("preparation_scope_reference")
                )
                or request.policy_learning_update_threshold.update_scope,
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
            if value is None or value == "" or value == ():
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
            if value is None or value == "" or value == ():
                continue
            snapshot[field_name] = self._to_text(value)
        return snapshot

    def _prohibited_update_approval_fields_present(
        self,
        field_names: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        present_fields: list[str] = []
        for field_name in field_names:
            value = context.get(field_name)
            if value is None or value == "":
                continue
            present_fields.append(field_name)
        return tuple(present_fields)

    def _approval_status(
        self,
        *,
        policy_learning_update_threshold: PolicyLearningUpdateThresholdRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_update_approval_fields: tuple[str, ...],
        prohibited_update_approval_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_update_approval_fields_present:
            return "prohibited_overlap_blocked"
        if missing_update_approval_fields:
            return "blocked_missing_context"
        if self._below_approval_threshold(
            policy_learning_update_threshold,
            class_definition,
            combined_context,
        ):
            return "rejected_for_policy_update_use"
        if self._requires_additional_governance_deferral(
            policy_learning_update_threshold,
            class_definition,
            combined_context,
        ):
            return "fallback_template_applied"
        if self._requires_preparation_restrictions(
            policy_learning_update_threshold,
            class_definition,
            combined_context,
        ):
            return "fallback_template_applied"
        if fallback_template_used:
            return "fallback_template_applied"
        return "approval_ready"

    def _below_approval_threshold(
        self,
        policy_learning_update_threshold: PolicyLearningUpdateThresholdRecord,
        class_definition,
        combined_context: Mapping[str, object],
    ) -> bool:
        if (
            policy_learning_update_threshold.policy_learning_update_threshold_status
            not in class_definition.allowed_policy_learning_update_threshold_statuses
        ):
            return True
        if (
            policy_learning_update_threshold.policy_learning_update_decision_outcome
            not in class_definition.allowed_policy_learning_update_decision_outcomes
        ):
            return True
        if (
            self._threshold_evidence_sufficiency_rank(
                policy_learning_update_threshold.evidence_sufficiency
            )
            < self._threshold_evidence_sufficiency_rank(
                class_definition.minimum_evidence_sufficiency
            )
        ):
            return True
        if (
            self._threshold_weak_evidence_check_rank(
                policy_learning_update_threshold.weak_evidence_check
            )
            < self._threshold_weak_evidence_check_rank(
                class_definition.minimum_weak_evidence_check
            )
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
        preparation_scope_restriction_reference = self._optional_text(
            combined_context.get("preparation_scope_restriction_reference")
        )
        if (
            (
                restriction_summary is not None
                or preparation_scope_restriction_reference is not None
                or policy_learning_update_threshold.policy_learning_update_decision_outcome
                == "accepted_with_narrowed_scope"
            )
            and not class_definition.allow_preparation_restrictions
        ):
            return True

        unresolved_governance_gaps = self._sequence_as_tuple(
            combined_context.get("unresolved_governance_gaps")
        )
        additional_governance_requirements = self._sequence_as_tuple(
            combined_context.get("additional_governance_requirements")
        )
        if (
            (
                unresolved_governance_gaps
                or additional_governance_requirements
                or policy_learning_update_threshold.policy_learning_update_decision_outcome
                == "deferred_for_continued_monitoring"
            )
            and not class_definition.allow_additional_governance_deferral
        ):
            return True

        return False

    def _requires_preparation_restrictions(
        self,
        policy_learning_update_threshold: PolicyLearningUpdateThresholdRecord,
        class_definition,
        combined_context: Mapping[str, object],
    ) -> bool:
        if not class_definition.allow_preparation_restrictions:
            return False
        if (
            policy_learning_update_threshold.policy_learning_update_decision_outcome
            == "accepted_with_narrowed_scope"
        ):
            return True
        if self._optional_text(combined_context.get("restriction_summary")) is not None:
            return True
        if (
            self._optional_text(
                combined_context.get("preparation_scope_restriction_reference")
            )
            is not None
        ):
            return True
        return False

    def _requires_additional_governance_deferral(
        self,
        policy_learning_update_threshold: PolicyLearningUpdateThresholdRecord,
        class_definition,
        combined_context: Mapping[str, object],
    ) -> bool:
        if not class_definition.allow_additional_governance_deferral:
            return False
        if (
            policy_learning_update_threshold.policy_learning_update_decision_outcome
            == "deferred_for_continued_monitoring"
        ):
            return True
        if self._sequence_as_tuple(
            combined_context.get("unresolved_governance_gaps")
        ):
            return True
        if self._sequence_as_tuple(
            combined_context.get("additional_governance_requirements")
        ):
            return True
        return False

    def _approval_outcome(
        self,
        *,
        template,
        approval_status: str,
    ) -> str:
        if approval_status in {
            "blocked_missing_context",
            "rejected_for_policy_update_use",
            "prohibited_overlap_blocked",
        }:
            return approval_status
        return template.policy_learning_update_approval_outcome

    def _reason(
        self,
        *,
        policy_learning_update_threshold: PolicyLearningUpdateThresholdRecord,
        approval_status: str,
        policy_learning_update_approval_class_id: str,
        missing_update_approval_fields: tuple[str, ...],
        prohibited_update_approval_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        approval_outcome: str,
    ) -> str:
        if approval_status == "blocked_missing_context":
            return (
                "Policy-learning update-approval review is missing required approval fields: "
                + ", ".join(missing_update_approval_fields)
                + "."
            )
        if approval_status == "prohibited_overlap_blocked":
            return (
                "Policy-learning update-approval class "
                f"'{policy_learning_update_approval_class_id}' cannot carry policy mutation, "
                "rollout, deployment, retraining, monitoring, reopen, orchestration, or lifecycle fields: "
                + ", ".join(prohibited_update_approval_fields_present)
                + "."
            )
        if approval_status == "rejected_for_policy_update_use":
            return (
                "Policy-learning update-approval class "
                f"'{policy_learning_update_approval_class_id}' rejected the threshold candidate "
                "because the upstream threshold posture or governance-readiness dimensions remain below the governed approval standard. "
                "Required minimums are threshold_status in "
                f"{class_definition.allowed_policy_learning_update_threshold_statuses}, threshold_outcome in "
                f"{class_definition.allowed_policy_learning_update_decision_outcomes}, evidence_sufficiency>="
                f"{class_definition.minimum_evidence_sufficiency}, weak_evidence_check>="
                f"{class_definition.minimum_weak_evidence_check}, and approval-dimension-strength>="
                f"{class_definition.minimum_dimension_strength}. Current upstream status is "
                f"'{policy_learning_update_threshold.policy_learning_update_threshold_status}' with outcome "
                f"'{policy_learning_update_threshold.policy_learning_update_decision_outcome}'."
            )
        if approval_outcome == "approved_with_restrictions":
            restriction_summary = self._optional_text(
                combined_context.get("restriction_summary")
            ) or "governed scope restrictions remain attached to update preparation"
            return (
                "Policy-learning update approval is granted only with explicit preparation restrictions because the upstream threshold candidate remains locally narrowed or otherwise constraint-bound. "
                f"Restriction summary: {restriction_summary}."
            )
        if approval_outcome == "deferred_pending_additional_governance":
            return (
                "Policy-learning update approval is deferred pending additional governance because unresolved governance gaps, required follow-up controls, or the upstream deferred threshold posture still prevent current approval for update preparation."
            )
        return (
            "Policy-learning update approval is complete and the governed threshold candidate is approved for policy-update preparation while preserving separate ownership for actual mutation, rollout, deployment, retraining, monitoring, and lifecycle handling."
        )

    def _lineage(
        self,
        request: PolicyLearningUpdateApprovalRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.policy_learning_update_threshold.lineage)
        lineage.update(
            {
                "policy_learning_update_threshold_id": (
                    request.policy_learning_update_threshold.policy_learning_update_threshold_id
                ),
                "policy_learning_update_approval_class_id": (
                    class_definition.policy_learning_update_approval_class_id
                ),
                "policy_learning_update_approval_class_version": (
                    class_definition.lineage.get("version", "unknown")
                ),
                "policy_learning_update_approval_template_id": (
                    template.policy_learning_update_approval_template_id
                ),
                "policy_learning_update_approval_template_version": (
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

    def _threshold_evidence_sufficiency_rank(self, evidence_sufficiency: str) -> int:
        return _THRESHOLD_EVIDENCE_SUFFICIENCY_RANK.get(evidence_sufficiency, -1)

    def _threshold_weak_evidence_check_rank(self, weak_evidence_check: str) -> int:
        return _THRESHOLD_WEAK_EVIDENCE_CHECK_RANK.get(weak_evidence_check, -1)

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

    def _to_text(self, value: object) -> str:
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)

    def _sequence_as_tuple(self, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            text = value.strip()
            return (text,) if text else ()
        if isinstance(value, (list, tuple)):
            result: list[str] = []
            for item in value:
                text = self._optional_text(item)
                if text is not None:
                    result.append(text)
            return tuple(result)
        text = self._optional_text(value)
        if text is None:
            return ()
        return (text,)
