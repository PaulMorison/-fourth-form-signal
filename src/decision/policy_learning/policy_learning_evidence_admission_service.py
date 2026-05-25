from __future__ import annotations

"""Deterministic policy-learning evidence admission after post-mortem judgment.

Canon ownership:
- Converts legitimate post-mortem judgments plus explicit evidence-admission
  context into governed policy-learning evidence-admission records.
- Owns admissibility status, canonical admission outcome, weak-evidence
  protection posture, attribution-readiness posture, and learning-gate lineage.
- Does not mutate policy, update models, monitor drift, reopen cases, or absorb
  orchestration ownership.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping, Sequence
from uuid import uuid4

from decision.policy_learning.policy_learning_evidence_admission_audit_adapter import (
    PolicyLearningEvidenceAdmissionAuditAdapter,
)
from decision.policy_learning.policy_learning_evidence_admission_registry import (
    PolicyLearningEvidenceAdmissionRegistry,
)
from decision.post_mortem.post_mortem_judgment_service import PostMortemJudgmentRecord

_EVIDENCE_QUALITY_RANK = {
    "insufficient_reconstructible_evidence": 0,
    "immature_observation_horizon": 1,
    "mixed_evidence_requires_caution": 2,
    "strong_reconstructible_evidence": 3,
}
_CONFIDENCE_POSTURE_RANK = {
    "insufficient_for_confident_judgment": 0,
    "cautious_for_review_only": 1,
    "confident_for_attribution": 2,
}
_BLOCKED_OUTCOME = "rejected_for_learning_use"


@dataclass(frozen=True)
class PolicyLearningEvidenceAdmissionRequest:
    post_mortem_judgment: PostMortemJudgmentRecord
    policy_learning_evidence_class_id: str
    policy_learning_evidence_author_role: str
    policy_learning_evidence_admission_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class PolicyLearningEvidenceAdmissionRecord:
    policy_learning_evidence_admission_id: str
    policy_learning_evidence_admission_status: str
    reason: str
    policy_learning_evidence_class_id: str
    policy_learning_evidence_template_id: str
    policy_learning_evidence_admission_outcome: str
    attribution_readiness: str
    evidence_sufficiency: str
    weak_evidence_protection: str
    post_mortem_judgment_id: str
    post_mortem_judgment_status: str
    post_mortem_judgment_class_id: str
    post_mortem_judgment_template_id: str
    primary_attribution_category: str
    post_mortem_evidence_quality: str
    post_mortem_confidence_posture: str
    post_mortem_learning_direction: str
    post_mortem_comparison_posture: str
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
    post_mortem_author_role: str
    post_mortem_author_id: str
    policy_learning_evidence_author_role: str
    policy_learning_evidence_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_evidence_fields: tuple[str, ...]
    optional_evidence_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_evidence_fields: tuple[str, ...]
    required_evidence_snapshot: Mapping[str, str]
    optional_evidence_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    domain_reference: str | None = None
    decision_scope_reference: str | None = None
    reporting_scope_reference: str | None = None
    tenant_scope_reference: str | None = None
    learning_scope_reference: str | None = None
    candidate_update_direction: str | None = None
    comparability_judgment: str | None = None
    commercial_interpretability_summary: str | None = None
    proposed_update_scope: str | None = None
    comparable_case_set_reference: str | None = None
    restriction_summary: str | None = None
    memory_object_reference: str | None = None
    review_threshold_id: str | None = None
    review_packet_id: str | None = None
    review_resolution_id: str | None = None
    recommendation_id: str | None = None
    policy_output_id: str | None = None
    portfolio_output_id: str | None = None
    action_instruction_id: str | None = None
    override_reference: str | None = None
    executed_action_reference: str | None = None
    realized_outcome_reference: str | None = None
    execution_deviation_reference: str | None = None
    competing_explanations: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    missing_evidence_fields: tuple[str, ...] = ()
    prohibited_evidence_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "policy_learning_evidence_admission_id": (
                self.policy_learning_evidence_admission_id
            ),
            "policy_learning_evidence_admission_status": (
                self.policy_learning_evidence_admission_status
            ),
            "reason": self.reason,
            "policy_learning_evidence_class_id": self.policy_learning_evidence_class_id,
            "policy_learning_evidence_template_id": (
                self.policy_learning_evidence_template_id
            ),
            "policy_learning_evidence_admission_outcome": (
                self.policy_learning_evidence_admission_outcome
            ),
            "attribution_readiness": self.attribution_readiness,
            "evidence_sufficiency": self.evidence_sufficiency,
            "weak_evidence_protection": self.weak_evidence_protection,
            "post_mortem_judgment_id": self.post_mortem_judgment_id,
            "post_mortem_judgment_status": self.post_mortem_judgment_status,
            "post_mortem_judgment_class_id": self.post_mortem_judgment_class_id,
            "post_mortem_judgment_template_id": (
                self.post_mortem_judgment_template_id
            ),
            "primary_attribution_category": self.primary_attribution_category,
            "post_mortem_evidence_quality": self.post_mortem_evidence_quality,
            "post_mortem_confidence_posture": self.post_mortem_confidence_posture,
            "post_mortem_learning_direction": self.post_mortem_learning_direction,
            "post_mortem_comparison_posture": self.post_mortem_comparison_posture,
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
            "post_mortem_author_role": self.post_mortem_author_role,
            "post_mortem_author_id": self.post_mortem_author_id,
            "policy_learning_evidence_author_role": (
                self.policy_learning_evidence_author_role
            ),
            "policy_learning_evidence_author_id": (
                self.policy_learning_evidence_author_id
            ),
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "required_evidence_fields": list(self.required_evidence_fields),
            "optional_evidence_fields": list(self.optional_evidence_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_evidence_fields": list(self.prohibited_evidence_fields),
            "required_evidence_snapshot": dict(self.required_evidence_snapshot),
            "optional_evidence_snapshot": dict(self.optional_evidence_snapshot),
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
        if self.candidate_update_direction is not None:
            payload["candidate_update_direction"] = self.candidate_update_direction
        if self.comparability_judgment is not None:
            payload["comparability_judgment"] = self.comparability_judgment
        if self.commercial_interpretability_summary is not None:
            payload["commercial_interpretability_summary"] = (
                self.commercial_interpretability_summary
            )
        if self.proposed_update_scope is not None:
            payload["proposed_update_scope"] = self.proposed_update_scope
        if self.comparable_case_set_reference is not None:
            payload["comparable_case_set_reference"] = (
                self.comparable_case_set_reference
            )
        if self.restriction_summary is not None:
            payload["restriction_summary"] = self.restriction_summary
        if self.memory_object_reference is not None:
            payload["memory_object_reference"] = self.memory_object_reference
        if self.review_threshold_id is not None:
            payload["review_threshold_id"] = self.review_threshold_id
        if self.review_packet_id is not None:
            payload["review_packet_id"] = self.review_packet_id
        if self.review_resolution_id is not None:
            payload["review_resolution_id"] = self.review_resolution_id
        if self.recommendation_id is not None:
            payload["recommendation_id"] = self.recommendation_id
        if self.policy_output_id is not None:
            payload["policy_output_id"] = self.policy_output_id
        if self.portfolio_output_id is not None:
            payload["portfolio_output_id"] = self.portfolio_output_id
        if self.action_instruction_id is not None:
            payload["action_instruction_id"] = self.action_instruction_id
        if self.override_reference is not None:
            payload["override_reference"] = self.override_reference
        if self.executed_action_reference is not None:
            payload["executed_action_reference"] = self.executed_action_reference
        if self.realized_outcome_reference is not None:
            payload["realized_outcome_reference"] = self.realized_outcome_reference
        if self.execution_deviation_reference is not None:
            payload["execution_deviation_reference"] = (
                self.execution_deviation_reference
            )
        if self.competing_explanations:
            payload["competing_explanations"] = list(self.competing_explanations)
        if self.evidence_gaps:
            payload["evidence_gaps"] = list(self.evidence_gaps)
        if self.missing_evidence_fields:
            payload["missing_evidence_fields"] = list(self.missing_evidence_fields)
        if self.prohibited_evidence_fields_present:
            payload["prohibited_evidence_fields_present"] = list(
                self.prohibited_evidence_fields_present
            )
        return payload

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "policy_learning_evidence_admission_id": (
                self.policy_learning_evidence_admission_id
            ),
            "policy_learning_evidence_template_id": (
                self.policy_learning_evidence_template_id
            ),
            "policy_learning_evidence_admission_outcome": (
                self.policy_learning_evidence_admission_outcome
            ),
            "attribution_readiness": self.attribution_readiness,
            "evidence_sufficiency": self.evidence_sufficiency,
            "weak_evidence_protection": self.weak_evidence_protection,
        }
        if self.learning_scope_reference is not None:
            context["learning_scope_reference"] = self.learning_scope_reference
        if self.candidate_update_direction is not None:
            context["candidate_update_direction"] = self.candidate_update_direction
        if self.comparability_judgment is not None:
            context["comparability_judgment"] = self.comparability_judgment
        if self.restriction_summary is not None:
            context["restriction_summary"] = self.restriction_summary
        return context


class PolicyLearningEvidenceAdmissionService:
    """Builds policy-learning evidence-admission records from post-mortems."""

    def __init__(
        self,
        *,
        policy_learning_evidence_admission_registry: PolicyLearningEvidenceAdmissionRegistry,
        policy_learning_evidence_admission_audit_adapter: PolicyLearningEvidenceAdmissionAuditAdapter,
    ) -> None:
        self._policy_learning_evidence_admission_registry = (
            policy_learning_evidence_admission_registry
        )
        self._policy_learning_evidence_admission_audit_adapter = (
            policy_learning_evidence_admission_audit_adapter
        )

    def generate(
        self,
        request: PolicyLearningEvidenceAdmissionRequest,
    ) -> PolicyLearningEvidenceAdmissionRecord:
        template, fallback_template_used = (
            self._policy_learning_evidence_admission_registry.resolve_template(
                semantic_scope=request.post_mortem_judgment.semantic_scope,
                post_mortem_judgment_class_id=(
                    request.post_mortem_judgment.post_mortem_judgment_class_id
                ),
                policy_learning_evidence_class_id=(
                    request.policy_learning_evidence_class_id
                ),
                route_name=request.post_mortem_judgment.lineage.get("route_name"),
            )
        )
        class_definition = (
            self._policy_learning_evidence_admission_registry.get_policy_learning_evidence_class(
                request.policy_learning_evidence_class_id
            )
        )
        combined_context = self._combined_context(request, class_definition)
        required_evidence_snapshot, missing_evidence_fields = (
            self._snapshot_required_fields(
                template.required_evidence_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(dict.fromkeys(missing_evidence_fields + missing_audit_fields))
        optional_evidence_snapshot = self._snapshot_optional_fields(
            template.optional_evidence_fields,
            combined_context,
        )
        prohibited_evidence_fields_present = self._prohibited_evidence_fields_present(
            class_definition.prohibited_evidence_fields,
            request.policy_learning_evidence_admission_context,
        )
        admission_status = self._admission_status(
            post_mortem_judgment=request.post_mortem_judgment,
            class_definition=class_definition,
            missing_evidence_fields=all_missing_fields,
            prohibited_evidence_fields_present=prohibited_evidence_fields_present,
            fallback_template_used=fallback_template_used,
        )
        admission_outcome = self._admission_outcome(
            template=template,
            admission_status=admission_status,
        )
        attribution_readiness = self._attribution_readiness(
            post_mortem_judgment=request.post_mortem_judgment,
            admission_status=admission_status,
        )
        evidence_sufficiency = self._evidence_sufficiency(
            admission_status=admission_status,
            admission_outcome=admission_outcome,
        )
        weak_evidence_protection = self._weak_evidence_protection(
            admission_status=admission_status,
            admission_outcome=admission_outcome,
        )
        reason = self._reason(
            post_mortem_judgment=request.post_mortem_judgment,
            admission_status=admission_status,
            policy_learning_evidence_class_id=(
                class_definition.policy_learning_evidence_class_id
            ),
            missing_evidence_fields=all_missing_fields,
            prohibited_evidence_fields_present=prohibited_evidence_fields_present,
            class_definition=class_definition,
        )

        lineage = self._lineage(request, class_definition, template)
        policy_learning_evidence_admission = PolicyLearningEvidenceAdmissionRecord(
            policy_learning_evidence_admission_id=str(uuid4()),
            policy_learning_evidence_admission_status=admission_status,
            reason=reason,
            policy_learning_evidence_class_id=(
                class_definition.policy_learning_evidence_class_id
            ),
            policy_learning_evidence_template_id=(
                template.policy_learning_evidence_template_id
            ),
            policy_learning_evidence_admission_outcome=admission_outcome,
            attribution_readiness=attribution_readiness,
            evidence_sufficiency=evidence_sufficiency,
            weak_evidence_protection=weak_evidence_protection,
            post_mortem_judgment_id=(
                request.post_mortem_judgment.post_mortem_judgment_id
            ),
            post_mortem_judgment_status=(
                request.post_mortem_judgment.post_mortem_status
            ),
            post_mortem_judgment_class_id=(
                request.post_mortem_judgment.post_mortem_judgment_class_id
            ),
            post_mortem_judgment_template_id=(
                request.post_mortem_judgment.post_mortem_judgment_template_id
            ),
            primary_attribution_category=(
                request.post_mortem_judgment.primary_attribution_category
            ),
            post_mortem_evidence_quality=request.post_mortem_judgment.evidence_quality,
            post_mortem_confidence_posture=(
                request.post_mortem_judgment.confidence_posture
            ),
            post_mortem_learning_direction=(
                request.post_mortem_judgment.learning_direction
            ),
            post_mortem_comparison_posture=(
                request.post_mortem_judgment.comparison_posture
            ),
            execution_outcome_id=request.post_mortem_judgment.execution_outcome_id,
            execution_outcome_status=(
                request.post_mortem_judgment.execution_outcome_status
            ),
            execution_outcome_class_id=(
                request.post_mortem_judgment.execution_outcome_class_id
            ),
            execution_dispatch_id=request.post_mortem_judgment.execution_dispatch_id,
            execution_dispatch_class_id=(
                request.post_mortem_judgment.execution_dispatch_class_id
            ),
            execution_request_id=request.post_mortem_judgment.execution_request_id,
            semantic_scope=request.post_mortem_judgment.semantic_scope,
            case_type=request.post_mortem_judgment.case_type,
            case_key=request.post_mortem_judgment.case_key,
            state_model_name=request.post_mortem_judgment.state_model_name,
            episode_id=request.post_mortem_judgment.episode_id,
            transition_name=request.post_mortem_judgment.transition_name,
            transition_class=request.post_mortem_judgment.transition_class,
            source_stage=request.post_mortem_judgment.source_stage,
            target_stage=request.post_mortem_judgment.target_stage,
            post_mortem_author_role=(
                request.post_mortem_judgment.post_mortem_author_role
            ),
            post_mortem_author_id=(
                request.post_mortem_judgment.post_mortem_author_id
            ),
            policy_learning_evidence_author_role=(
                request.policy_learning_evidence_author_role
            ),
            policy_learning_evidence_author_id=request.actor_id,
            authority_resolution_kind=(
                request.post_mortem_judgment.authority_resolution_kind
            ),
            authority_review_required=(
                request.post_mortem_judgment.authority_review_required
            ),
            router_rule_id=request.post_mortem_judgment.router_rule_id,
            routing_resolution_status=(
                request.post_mortem_judgment.routing_resolution_status
            ),
            routing_review_required=(
                request.post_mortem_judgment.routing_review_required
            ),
            review_mode=request.post_mortem_judgment.review_mode,
            required_evidence_fields=template.required_evidence_fields,
            optional_evidence_fields=template.optional_evidence_fields,
            required_audit_fields=template.required_audit_fields,
            prohibited_evidence_fields=class_definition.prohibited_evidence_fields,
            required_evidence_snapshot=required_evidence_snapshot,
            optional_evidence_snapshot=optional_evidence_snapshot,
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
            candidate_update_direction=self._optional_text(
                combined_context.get("candidate_update_direction")
            ),
            comparability_judgment=self._optional_text(
                combined_context.get("comparability_judgment")
            ),
            commercial_interpretability_summary=self._optional_text(
                combined_context.get("commercial_interpretability_summary")
            ),
            proposed_update_scope=self._optional_text(
                combined_context.get("proposed_update_scope")
            ),
            comparable_case_set_reference=self._optional_text(
                combined_context.get("comparable_case_set_reference")
            ),
            restriction_summary=self._optional_text(
                combined_context.get("restriction_summary")
            ),
            memory_object_reference=self._optional_text(
                combined_context.get("memory_object_reference")
            ),
            review_threshold_id=self._optional_text(lineage.get("threshold_id")),
            review_packet_id=self._optional_text(lineage.get("review_packet_id")),
            review_resolution_id=self._optional_text(
                lineage.get("review_resolution_id")
            ),
            recommendation_id=self._optional_text(lineage.get("recommendation_id")),
            policy_output_id=self._optional_text(lineage.get("policy_output_id")),
            portfolio_output_id=self._optional_text(
                lineage.get("portfolio_output_id")
            ),
            action_instruction_id=self._optional_text(
                lineage.get("action_instruction_id")
            ),
            override_reference=self._optional_text(
                combined_context.get("override_reference")
            ),
            executed_action_reference=self._optional_text(
                combined_context.get("executed_action_reference")
            ),
            realized_outcome_reference=self._optional_text(
                combined_context.get("realized_outcome_reference")
            ),
            execution_deviation_reference=self._optional_text(
                combined_context.get("execution_deviation_reference")
            ),
            competing_explanations=self._sequence_as_tuple(
                combined_context.get("competing_explanations")
            ),
            evidence_gaps=self._sequence_as_tuple(
                combined_context.get("evidence_gaps")
            ),
            missing_evidence_fields=all_missing_fields,
            prohibited_evidence_fields_present=prohibited_evidence_fields_present,
        )
        self._policy_learning_evidence_admission_audit_adapter.record_policy_learning_evidence_admission(
            policy_learning_evidence_admission,
            request=request,
        )
        return policy_learning_evidence_admission

    def _combined_context(
        self,
        request: PolicyLearningEvidenceAdmissionRequest,
        class_definition,
    ) -> dict[str, object]:
        context = dict(request.post_mortem_judgment.required_post_mortem_snapshot)
        context.update(request.post_mortem_judgment.optional_post_mortem_snapshot)
        context.update(request.post_mortem_judgment.required_audit_snapshot)
        context.update(dict(request.policy_learning_evidence_admission_context))
        context.update(
            {
                "policy_learning_evidence_class_id": (
                    class_definition.policy_learning_evidence_class_id
                ),
                "policy_learning_evidence_author_id": request.actor_id,
                "policy_learning_evidence_author_role": (
                    request.policy_learning_evidence_author_role
                ),
                "domain_reference": self._optional_text(context.get("domain_reference"))
                or request.post_mortem_judgment.domain_reference
                or request.post_mortem_judgment.semantic_scope,
                "decision_scope_reference": self._optional_text(
                    context.get("decision_scope_reference")
                )
                or request.post_mortem_judgment.decision_scope_reference
                or "",
                "tenant_scope_reference": self._optional_text(
                    context.get("tenant_scope_reference")
                )
                or request.post_mortem_judgment.tenant_scope_reference
                or "",
                "reporting_scope_reference": self._optional_text(
                    context.get("reporting_scope_reference")
                )
                or request.post_mortem_judgment.reporting_scope_reference
                or "",
                "executed_action_reference": self._optional_text(
                    context.get("executed_action_reference")
                )
                or request.post_mortem_judgment.executed_action_reference
                or "",
                "realized_outcome_reference": self._optional_text(
                    context.get("realized_outcome_reference")
                )
                or request.post_mortem_judgment.realized_outcome_reference
                or "",
                "execution_deviation_reference": self._optional_text(
                    context.get("execution_deviation_reference")
                )
                or request.post_mortem_judgment.execution_deviation_reference
                or "",
                "override_reference": self._optional_text(
                    context.get("override_reference")
                )
                or request.post_mortem_judgment.override_reference
                or "",
                "learning_scope_reference": self._optional_text(
                    context.get("learning_scope_reference")
                )
                or "",
                "candidate_update_direction": self._optional_text(
                    context.get("candidate_update_direction")
                )
                or "",
                "comparability_judgment": self._optional_text(
                    context.get("comparability_judgment")
                )
                or "",
                "commercial_interpretability_summary": self._optional_text(
                    context.get("commercial_interpretability_summary")
                )
                or "",
                "proposed_update_scope": self._optional_text(
                    context.get("proposed_update_scope")
                )
                or "",
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

    def _prohibited_evidence_fields_present(
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

    def _admission_status(
        self,
        *,
        post_mortem_judgment: PostMortemJudgmentRecord,
        class_definition,
        missing_evidence_fields: tuple[str, ...],
        prohibited_evidence_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_evidence_fields_present:
            return "prohibited_overlap_blocked"
        if missing_evidence_fields:
            return "blocked_missing_context"
        if self._below_threshold(post_mortem_judgment, class_definition):
            return "blocked_insufficient_evidence"
        if fallback_template_used:
            return "fallback_template_applied"
        return "admitted_ready"

    def _below_threshold(
        self,
        post_mortem_judgment: PostMortemJudgmentRecord,
        class_definition,
    ) -> bool:
        if (
            post_mortem_judgment.post_mortem_judgment_class_id
            not in class_definition.allowed_post_mortem_judgment_class_ids
        ):
            return True
        if (
            post_mortem_judgment.post_mortem_status
            not in class_definition.allowed_post_mortem_statuses
        ):
            return True
        if self._evidence_rank(post_mortem_judgment.evidence_quality) < self._evidence_rank(
            class_definition.minimum_evidence_quality
        ):
            return True
        if self._confidence_rank(post_mortem_judgment.confidence_posture) < self._confidence_rank(
            class_definition.minimum_confidence_posture
        ):
            return True
        return False

    def _admission_outcome(
        self,
        *,
        template,
        admission_status: str,
    ) -> str:
        if admission_status in {
            "blocked_missing_context",
            "blocked_insufficient_evidence",
            "prohibited_overlap_blocked",
        }:
            return _BLOCKED_OUTCOME
        return template.policy_learning_evidence_admission_outcome

    def _attribution_readiness(
        self,
        *,
        post_mortem_judgment: PostMortemJudgmentRecord,
        admission_status: str,
    ) -> str:
        if admission_status == "admitted_ready":
            return "attribution_ready_for_learning"
        if admission_status == "fallback_template_applied":
            return "attribution_pending_more_evidence"
        if post_mortem_judgment.confidence_posture == "cautious_for_review_only":
            return "attribution_restricted_for_learning"
        return "attribution_not_ready_for_learning"

    def _evidence_sufficiency(
        self,
        *,
        admission_status: str,
        admission_outcome: str,
    ) -> str:
        if admission_status == "admitted_ready":
            return "learning_grade_evidence_sufficient"
        if admission_status == "fallback_template_applied":
            if admission_outcome == "admitted_with_restrictions":
                return "learning_evidence_restricted"
            return "learning_evidence_deferred"
        if admission_status == "blocked_missing_context":
            return "learning_evidence_incomplete"
        if admission_status == "prohibited_overlap_blocked":
            return "learning_evidence_overlap_prohibited"
        return "insufficient_for_learning_admission"

    def _weak_evidence_protection(
        self,
        *,
        admission_status: str,
        admission_outcome: str,
    ) -> str:
        if admission_status == "admitted_ready":
            return "weak_evidence_protection_passed"
        if admission_status == "fallback_template_applied":
            if admission_outcome == "admitted_with_restrictions":
                return "weak_evidence_protection_restricted_scope"
            return "weak_evidence_protection_deferred"
        if admission_status == "prohibited_overlap_blocked":
            return "weak_evidence_protection_blocked_overlap"
        return "weak_evidence_protection_blocked"

    def _reason(
        self,
        *,
        post_mortem_judgment: PostMortemJudgmentRecord,
        admission_status: str,
        policy_learning_evidence_class_id: str,
        missing_evidence_fields: tuple[str, ...],
        prohibited_evidence_fields_present: tuple[str, ...],
        class_definition,
    ) -> str:
        if admission_status == "blocked_missing_context":
            return (
                "Policy-learning evidence admission is missing required evidence fields: "
                + ", ".join(missing_evidence_fields)
                + "."
            )
        if admission_status == "prohibited_overlap_blocked":
            return (
                "Policy-learning evidence class "
                f"'{policy_learning_evidence_class_id}' cannot carry reopen, monitoring, "
                "model-mutation, deployment, or policy-execution fields: "
                + ", ".join(prohibited_evidence_fields_present)
                + "."
            )
        if admission_status == "blocked_insufficient_evidence":
            return (
                "Policy-learning evidence class "
                f"'{policy_learning_evidence_class_id}' rejected the post-mortem evidence "
                "because post-mortem status, evidence quality, or confidence posture is "
                "below the governed admission threshold. Required minimums are "
                f"status in {class_definition.allowed_post_mortem_statuses}, "
                f"evidence_quality>={class_definition.minimum_evidence_quality}, and "
                f"confidence_posture>={class_definition.minimum_confidence_posture}."
            )
        if admission_status == "fallback_template_applied":
            return (
                "A governed fallback evidence-admission template was applied because the "
                "post-mortem record is structurally meaningful but still deferred pending "
                "more evidence before update-threshold review."
            )
        return (
            "Policy-learning evidence admission is complete and ready to enter governed "
            "update-threshold review."
        )

    def _lineage(
        self,
        request: PolicyLearningEvidenceAdmissionRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.post_mortem_judgment.lineage)
        lineage.update(
            {
                "post_mortem_judgment_id": (
                    request.post_mortem_judgment.post_mortem_judgment_id
                ),
                "post_mortem_judgment_class_id": (
                    request.post_mortem_judgment.post_mortem_judgment_class_id
                ),
                "post_mortem_judgment_template_id": (
                    request.post_mortem_judgment.post_mortem_judgment_template_id
                ),
                "policy_learning_evidence_class_id": (
                    class_definition.policy_learning_evidence_class_id
                ),
                "policy_learning_evidence_class_version": (
                    class_definition.lineage.get("version", "unknown")
                ),
                "policy_learning_evidence_template_id": (
                    template.policy_learning_evidence_template_id
                ),
                "policy_learning_evidence_template_version": (
                    template.lineage.get("version", "unknown")
                ),
            }
        )
        return lineage

    def _evidence_rank(self, evidence_quality: str) -> int:
        return _EVIDENCE_QUALITY_RANK.get(evidence_quality, -1)

    def _confidence_rank(self, confidence_posture: str) -> int:
        return _CONFIDENCE_POSTURE_RANK.get(confidence_posture, -1)

    def _optional_text(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return self._to_text(value)

    def _sequence_as_tuple(self, value: object) -> tuple[str, ...]:
        if value is None or value == "" or value == ():
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, Sequence):
            return tuple(self._to_text(item) for item in value if item not in {None, ""})
        return (self._to_text(value),)

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)