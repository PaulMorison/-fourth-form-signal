from __future__ import annotations

"""Deterministic policy-learning update-threshold review after evidence admission.

Canon ownership:
- Converts admitted policy-learning evidence plus explicit threshold context
  into governed policy-learning update-threshold records.
- Owns update-decision outcome meaning, evidence sufficiency matched to
  update severity, weak-evidence check posture, bounded narrowing posture,
  and update-threshold lineage.
- Does not mutate policy, execute policy updates, retrain or deploy models,
  monitor drift, reopen cases, or absorb orchestration or lifecycle meaning.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping, Sequence
from uuid import uuid4

from decision.policy_learning.policy_learning_evidence_admission_service import (
    PolicyLearningEvidenceAdmissionRecord,
)
from decision.policy_learning.policy_learning_update_threshold_audit_adapter import (
    PolicyLearningUpdateThresholdAuditAdapter,
)
from decision.policy_learning.policy_learning_update_threshold_registry import (
    PolicyLearningUpdateThresholdRegistry,
)

_POLICY_LEARNING_EVIDENCE_SUFFICIENCY_RANK = {
    "insufficient_for_learning_admission": 0,
    "learning_evidence_overlap_prohibited": 0,
    "learning_evidence_incomplete": 1,
    "learning_evidence_deferred": 2,
    "learning_evidence_restricted": 3,
    "learning_grade_evidence_sufficient": 4,
}
_POLICY_LEARNING_EVIDENCE_ATTRIBUTION_READINESS_RANK = {
    "attribution_not_ready_for_learning": 0,
    "attribution_pending_more_evidence": 1,
    "attribution_restricted_for_learning": 2,
    "attribution_ready_for_learning": 3,
}
_DIMENSION_STRENGTH_RANK = {
    "weak": 0,
    "moderate": 1,
    "strong": 2,
}
_REPETITION_POSTURE_RANK = {
    "single_case_only": 0,
    "limited_repetition": 1,
    "exceptional_single_case": 1,
    "repeated_comparable_cases": 2,
}
_UPDATE_SEVERITY_DIMENSION_RANK = {
    "calibration_refinement": 1,
    "local_policy_adjustment": 1,
    "broad_policy_change": 2,
    "governance_sensitive_change": 2,
}
_UPDATE_SEVERITY_REPETITION_RANK = {
    "calibration_refinement": 1,
    "local_policy_adjustment": 1,
    "broad_policy_change": 2,
    "governance_sensitive_change": 2,
}
_BLOCKED_OUTCOME = "rejected"
_DIMENSION_FIELDS = (
    "evidence_completeness",
    "evidence_consistency",
    "evidence_comparability",
    "attribution_quality",
    "scope_legitimacy",
    "transfer_validity",
    "magnitude_alignment",
)


@dataclass(frozen=True)
class PolicyLearningUpdateThresholdRequest:
    policy_learning_evidence_admission: PolicyLearningEvidenceAdmissionRecord
    policy_learning_update_threshold_class_id: str
    policy_learning_update_threshold_author_role: str
    policy_learning_update_threshold_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class PolicyLearningUpdateThresholdRecord:
    policy_learning_update_threshold_id: str
    policy_learning_update_threshold_status: str
    reason: str
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
    policy_learning_evidence_attribution_readiness: str
    policy_learning_evidence_sufficiency: str
    policy_learning_evidence_weak_evidence_protection: str
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
    policy_learning_evidence_author_role: str
    policy_learning_evidence_author_id: str
    policy_learning_update_threshold_author_role: str
    policy_learning_update_threshold_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_update_threshold_fields: tuple[str, ...]
    optional_update_threshold_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_update_threshold_fields: tuple[str, ...]
    required_update_threshold_snapshot: Mapping[str, str]
    optional_update_threshold_snapshot: Mapping[str, str]
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
    evidence_base_summary: str | None = None
    evidence_completeness: str | None = None
    evidence_consistency: str | None = None
    evidence_comparability: str | None = None
    attribution_quality: str | None = None
    scope_legitimacy: str | None = None
    transfer_validity: str | None = None
    magnitude_alignment: str | None = None
    repetition_posture: str | None = None
    commercial_significance: str | None = None
    governance_sensitivity: str | None = None
    local_contradiction_posture: str | None = None
    narrowed_scope_reference: str | None = None
    monitoring_recommendation: str | None = None
    unresolved_competing_explanations: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    missing_update_threshold_fields: tuple[str, ...] = ()
    prohibited_update_threshold_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "policy_learning_update_threshold_id": (
                self.policy_learning_update_threshold_id
            ),
            "policy_learning_update_threshold_status": (
                self.policy_learning_update_threshold_status
            ),
            "reason": self.reason,
            "policy_learning_update_threshold_class_id": (
                self.policy_learning_update_threshold_class_id
            ),
            "policy_learning_update_threshold_template_id": (
                self.policy_learning_update_threshold_template_id
            ),
            "policy_learning_update_decision_outcome": (
                self.policy_learning_update_decision_outcome
            ),
            "evidence_sufficiency": self.evidence_sufficiency,
            "weak_evidence_check": self.weak_evidence_check,
            "policy_behavior_change": self.policy_behavior_change,
            "update_severity": self.update_severity,
            "update_scope": self.update_scope,
            "policy_learning_evidence_admission_id": (
                self.policy_learning_evidence_admission_id
            ),
            "policy_learning_evidence_admission_status": (
                self.policy_learning_evidence_admission_status
            ),
            "policy_learning_evidence_class_id": self.policy_learning_evidence_class_id,
            "policy_learning_evidence_template_id": (
                self.policy_learning_evidence_template_id
            ),
            "policy_learning_evidence_admission_outcome": (
                self.policy_learning_evidence_admission_outcome
            ),
            "policy_learning_evidence_attribution_readiness": (
                self.policy_learning_evidence_attribution_readiness
            ),
            "policy_learning_evidence_sufficiency": (
                self.policy_learning_evidence_sufficiency
            ),
            "policy_learning_evidence_weak_evidence_protection": (
                self.policy_learning_evidence_weak_evidence_protection
            ),
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
            "policy_learning_evidence_author_role": (
                self.policy_learning_evidence_author_role
            ),
            "policy_learning_evidence_author_id": self.policy_learning_evidence_author_id,
            "policy_learning_update_threshold_author_role": (
                self.policy_learning_update_threshold_author_role
            ),
            "policy_learning_update_threshold_author_id": (
                self.policy_learning_update_threshold_author_id
            ),
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "required_update_threshold_fields": list(
                self.required_update_threshold_fields
            ),
            "optional_update_threshold_fields": list(
                self.optional_update_threshold_fields
            ),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_update_threshold_fields": list(
                self.prohibited_update_threshold_fields
            ),
            "required_update_threshold_snapshot": dict(
                self.required_update_threshold_snapshot
            ),
            "optional_update_threshold_snapshot": dict(
                self.optional_update_threshold_snapshot
            ),
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
        if self.evidence_base_summary is not None:
            payload["evidence_base_summary"] = self.evidence_base_summary
        if self.evidence_completeness is not None:
            payload["evidence_completeness"] = self.evidence_completeness
        if self.evidence_consistency is not None:
            payload["evidence_consistency"] = self.evidence_consistency
        if self.evidence_comparability is not None:
            payload["evidence_comparability"] = self.evidence_comparability
        if self.attribution_quality is not None:
            payload["attribution_quality"] = self.attribution_quality
        if self.scope_legitimacy is not None:
            payload["scope_legitimacy"] = self.scope_legitimacy
        if self.transfer_validity is not None:
            payload["transfer_validity"] = self.transfer_validity
        if self.magnitude_alignment is not None:
            payload["magnitude_alignment"] = self.magnitude_alignment
        if self.repetition_posture is not None:
            payload["repetition_posture"] = self.repetition_posture
        if self.commercial_significance is not None:
            payload["commercial_significance"] = self.commercial_significance
        if self.governance_sensitivity is not None:
            payload["governance_sensitivity"] = self.governance_sensitivity
        if self.local_contradiction_posture is not None:
            payload["local_contradiction_posture"] = (
                self.local_contradiction_posture
            )
        if self.narrowed_scope_reference is not None:
            payload["narrowed_scope_reference"] = self.narrowed_scope_reference
        if self.monitoring_recommendation is not None:
            payload["monitoring_recommendation"] = self.monitoring_recommendation
        if self.unresolved_competing_explanations:
            payload["unresolved_competing_explanations"] = list(
                self.unresolved_competing_explanations
            )
        if self.evidence_gaps:
            payload["evidence_gaps"] = list(self.evidence_gaps)
        if self.missing_update_threshold_fields:
            payload["missing_update_threshold_fields"] = list(
                self.missing_update_threshold_fields
            )
        if self.prohibited_update_threshold_fields_present:
            payload["prohibited_update_threshold_fields_present"] = list(
                self.prohibited_update_threshold_fields_present
            )
        return payload

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "policy_learning_update_threshold_id": (
                self.policy_learning_update_threshold_id
            ),
            "policy_learning_update_threshold_template_id": (
                self.policy_learning_update_threshold_template_id
            ),
            "policy_learning_update_decision_outcome": (
                self.policy_learning_update_decision_outcome
            ),
            "evidence_sufficiency": self.evidence_sufficiency,
            "weak_evidence_check": self.weak_evidence_check,
        }
        if self.narrowed_scope_reference is not None:
            context["narrowed_scope_reference"] = self.narrowed_scope_reference
        if self.monitoring_recommendation is not None:
            context["monitoring_recommendation"] = self.monitoring_recommendation
        return context


class PolicyLearningUpdateThresholdService:
    """Builds policy-learning update-threshold records from admitted evidence."""

    def __init__(
        self,
        *,
        policy_learning_update_threshold_registry: PolicyLearningUpdateThresholdRegistry,
        policy_learning_update_threshold_audit_adapter: PolicyLearningUpdateThresholdAuditAdapter,
    ) -> None:
        self._policy_learning_update_threshold_registry = (
            policy_learning_update_threshold_registry
        )
        self._policy_learning_update_threshold_audit_adapter = (
            policy_learning_update_threshold_audit_adapter
        )

    def generate(
        self,
        request: PolicyLearningUpdateThresholdRequest,
    ) -> PolicyLearningUpdateThresholdRecord:
        template, fallback_template_used = (
            self._policy_learning_update_threshold_registry.resolve_template(
                semantic_scope=request.policy_learning_evidence_admission.semantic_scope,
                policy_learning_evidence_class_id=(
                    request.policy_learning_evidence_admission.policy_learning_evidence_class_id
                ),
                policy_learning_update_threshold_class_id=(
                    request.policy_learning_update_threshold_class_id
                ),
                route_name=request.policy_learning_evidence_admission.lineage.get(
                    "route_name"
                ),
            )
        )
        class_definition = (
            self._policy_learning_update_threshold_registry.get_policy_learning_update_threshold_class(
                request.policy_learning_update_threshold_class_id
            )
        )
        combined_context = self._combined_context(request, class_definition)
        required_update_threshold_snapshot, missing_update_threshold_fields = (
            self._snapshot_required_fields(
                template.required_update_threshold_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_update_threshold_fields + missing_audit_fields)
        )
        optional_update_threshold_snapshot = self._snapshot_optional_fields(
            template.optional_update_threshold_fields,
            combined_context,
        )
        prohibited_update_threshold_fields_present = (
            self._prohibited_update_threshold_fields_present(
                class_definition.prohibited_update_threshold_fields,
                request.policy_learning_update_threshold_context,
            )
        )
        threshold_status = self._threshold_status(
            policy_learning_evidence_admission=request.policy_learning_evidence_admission,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_update_threshold_fields=all_missing_fields,
            prohibited_update_threshold_fields_present=(
                prohibited_update_threshold_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        decision_outcome = self._decision_outcome(
            template=template,
            threshold_status=threshold_status,
        )
        evidence_sufficiency = self._evidence_sufficiency(
            threshold_status=threshold_status,
            decision_outcome=decision_outcome,
        )
        weak_evidence_check = self._weak_evidence_check(
            threshold_status=threshold_status,
            decision_outcome=decision_outcome,
        )
        reason = self._reason(
            policy_learning_evidence_admission=(
                request.policy_learning_evidence_admission
            ),
            threshold_status=threshold_status,
            policy_learning_update_threshold_class_id=(
                class_definition.policy_learning_update_threshold_class_id
            ),
            missing_update_threshold_fields=all_missing_fields,
            prohibited_update_threshold_fields_present=(
                prohibited_update_threshold_fields_present
            ),
            class_definition=class_definition,
        )
        lineage = self._lineage(request, class_definition, template)

        policy_learning_update_threshold = PolicyLearningUpdateThresholdRecord(
            policy_learning_update_threshold_id=str(uuid4()),
            policy_learning_update_threshold_status=threshold_status,
            reason=reason,
            policy_learning_update_threshold_class_id=(
                class_definition.policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_template_id=(
                template.policy_learning_update_threshold_template_id
            ),
            policy_learning_update_decision_outcome=decision_outcome,
            evidence_sufficiency=evidence_sufficiency,
            weak_evidence_check=weak_evidence_check,
            policy_behavior_change=self._field_value_or_placeholder(
                field_name="policy_behavior_change",
                snapshot=required_update_threshold_snapshot,
                context=combined_context,
            ),
            update_severity=self._field_value_or_placeholder(
                field_name="update_severity",
                snapshot=required_update_threshold_snapshot,
                context=combined_context,
            ),
            update_scope=self._field_value_or_placeholder(
                field_name="update_scope",
                snapshot=required_update_threshold_snapshot,
                context=combined_context,
            ),
            policy_learning_evidence_admission_id=(
                request.policy_learning_evidence_admission.policy_learning_evidence_admission_id
            ),
            policy_learning_evidence_admission_status=(
                request.policy_learning_evidence_admission.policy_learning_evidence_admission_status
            ),
            policy_learning_evidence_class_id=(
                request.policy_learning_evidence_admission.policy_learning_evidence_class_id
            ),
            policy_learning_evidence_template_id=(
                request.policy_learning_evidence_admission.policy_learning_evidence_template_id
            ),
            policy_learning_evidence_admission_outcome=(
                request.policy_learning_evidence_admission.policy_learning_evidence_admission_outcome
            ),
            policy_learning_evidence_attribution_readiness=(
                request.policy_learning_evidence_admission.attribution_readiness
            ),
            policy_learning_evidence_sufficiency=(
                request.policy_learning_evidence_admission.evidence_sufficiency
            ),
            policy_learning_evidence_weak_evidence_protection=(
                request.policy_learning_evidence_admission.weak_evidence_protection
            ),
            post_mortem_judgment_id=(
                request.policy_learning_evidence_admission.post_mortem_judgment_id
            ),
            post_mortem_judgment_status=(
                request.policy_learning_evidence_admission.post_mortem_judgment_status
            ),
            post_mortem_judgment_class_id=(
                request.policy_learning_evidence_admission.post_mortem_judgment_class_id
            ),
            post_mortem_judgment_template_id=(
                request.policy_learning_evidence_admission.post_mortem_judgment_template_id
            ),
            primary_attribution_category=(
                request.policy_learning_evidence_admission.primary_attribution_category
            ),
            post_mortem_evidence_quality=(
                request.policy_learning_evidence_admission.post_mortem_evidence_quality
            ),
            post_mortem_confidence_posture=(
                request.policy_learning_evidence_admission.post_mortem_confidence_posture
            ),
            post_mortem_learning_direction=(
                request.policy_learning_evidence_admission.post_mortem_learning_direction
            ),
            post_mortem_comparison_posture=(
                request.policy_learning_evidence_admission.post_mortem_comparison_posture
            ),
            execution_outcome_id=(
                request.policy_learning_evidence_admission.execution_outcome_id
            ),
            execution_outcome_status=(
                request.policy_learning_evidence_admission.execution_outcome_status
            ),
            execution_outcome_class_id=(
                request.policy_learning_evidence_admission.execution_outcome_class_id
            ),
            execution_dispatch_id=(
                request.policy_learning_evidence_admission.execution_dispatch_id
            ),
            execution_dispatch_class_id=(
                request.policy_learning_evidence_admission.execution_dispatch_class_id
            ),
            execution_request_id=(
                request.policy_learning_evidence_admission.execution_request_id
            ),
            semantic_scope=request.policy_learning_evidence_admission.semantic_scope,
            case_type=request.policy_learning_evidence_admission.case_type,
            case_key=request.policy_learning_evidence_admission.case_key,
            state_model_name=request.policy_learning_evidence_admission.state_model_name,
            episode_id=request.policy_learning_evidence_admission.episode_id,
            transition_name=request.policy_learning_evidence_admission.transition_name,
            transition_class=request.policy_learning_evidence_admission.transition_class,
            source_stage=request.policy_learning_evidence_admission.source_stage,
            target_stage=request.policy_learning_evidence_admission.target_stage,
            policy_learning_evidence_author_role=(
                request.policy_learning_evidence_admission.policy_learning_evidence_author_role
            ),
            policy_learning_evidence_author_id=(
                request.policy_learning_evidence_admission.policy_learning_evidence_author_id
            ),
            policy_learning_update_threshold_author_role=(
                request.policy_learning_update_threshold_author_role
            ),
            policy_learning_update_threshold_author_id=request.actor_id,
            authority_resolution_kind=(
                request.policy_learning_evidence_admission.authority_resolution_kind
            ),
            authority_review_required=(
                request.policy_learning_evidence_admission.authority_review_required
            ),
            router_rule_id=request.policy_learning_evidence_admission.router_rule_id,
            routing_resolution_status=(
                request.policy_learning_evidence_admission.routing_resolution_status
            ),
            routing_review_required=(
                request.policy_learning_evidence_admission.routing_review_required
            ),
            review_mode=request.policy_learning_evidence_admission.review_mode,
            required_update_threshold_fields=(
                template.required_update_threshold_fields
            ),
            optional_update_threshold_fields=(
                template.optional_update_threshold_fields
            ),
            required_audit_fields=template.required_audit_fields,
            prohibited_update_threshold_fields=(
                class_definition.prohibited_update_threshold_fields
            ),
            required_update_threshold_snapshot=required_update_threshold_snapshot,
            optional_update_threshold_snapshot=optional_update_threshold_snapshot,
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
            evidence_base_summary=self._optional_text(
                combined_context.get("evidence_base_summary")
            ),
            evidence_completeness=self._optional_text(
                combined_context.get("evidence_completeness")
            ),
            evidence_consistency=self._optional_text(
                combined_context.get("evidence_consistency")
            ),
            evidence_comparability=self._optional_text(
                combined_context.get("evidence_comparability")
            ),
            attribution_quality=self._optional_text(
                combined_context.get("attribution_quality")
            ),
            scope_legitimacy=self._optional_text(
                combined_context.get("scope_legitimacy")
            ),
            transfer_validity=self._optional_text(
                combined_context.get("transfer_validity")
            ),
            magnitude_alignment=self._optional_text(
                combined_context.get("magnitude_alignment")
            ),
            repetition_posture=self._optional_text(
                combined_context.get("repetition_posture")
            ),
            commercial_significance=self._optional_text(
                combined_context.get("commercial_significance")
            ),
            governance_sensitivity=self._optional_text(
                combined_context.get("governance_sensitivity")
            ),
            local_contradiction_posture=self._optional_text(
                combined_context.get("local_contradiction_posture")
            ),
            narrowed_scope_reference=self._optional_text(
                combined_context.get("narrowed_scope_reference")
            ),
            monitoring_recommendation=self._optional_text(
                combined_context.get("monitoring_recommendation")
            ),
            unresolved_competing_explanations=self._sequence_as_tuple(
                combined_context.get("unresolved_competing_explanations")
            ),
            evidence_gaps=self._sequence_as_tuple(combined_context.get("evidence_gaps")),
            missing_update_threshold_fields=all_missing_fields,
            prohibited_update_threshold_fields_present=(
                prohibited_update_threshold_fields_present
            ),
        )
        self._policy_learning_update_threshold_audit_adapter.record_policy_learning_update_threshold(
            policy_learning_update_threshold,
            request=request,
        )
        return policy_learning_update_threshold

    def _combined_context(
        self,
        request: PolicyLearningUpdateThresholdRequest,
        class_definition,
    ) -> dict[str, object]:
        context = dict(
            request.policy_learning_evidence_admission.required_evidence_snapshot
        )
        context.update(
            request.policy_learning_evidence_admission.optional_evidence_snapshot
        )
        context.update(request.policy_learning_evidence_admission.required_audit_snapshot)
        context.update(dict(request.policy_learning_update_threshold_context))
        context.update(
            {
                "policy_learning_update_threshold_class_id": (
                    class_definition.policy_learning_update_threshold_class_id
                ),
                "policy_learning_update_threshold_author_id": request.actor_id,
                "policy_learning_update_threshold_author_role": (
                    request.policy_learning_update_threshold_author_role
                ),
                "domain_reference": self._optional_text(context.get("domain_reference"))
                or request.policy_learning_evidence_admission.domain_reference
                or request.policy_learning_evidence_admission.semantic_scope,
                "decision_scope_reference": self._optional_text(
                    context.get("decision_scope_reference")
                )
                or request.policy_learning_evidence_admission.decision_scope_reference
                or "",
                "tenant_scope_reference": self._optional_text(
                    context.get("tenant_scope_reference")
                )
                or request.policy_learning_evidence_admission.tenant_scope_reference
                or "",
                "reporting_scope_reference": self._optional_text(
                    context.get("reporting_scope_reference")
                )
                or request.policy_learning_evidence_admission.reporting_scope_reference
                or "",
                "learning_scope_reference": self._optional_text(
                    context.get("learning_scope_reference")
                )
                or request.policy_learning_evidence_admission.learning_scope_reference
                or "",
                "candidate_update_direction": self._optional_text(
                    context.get("candidate_update_direction")
                )
                or request.policy_learning_evidence_admission.candidate_update_direction
                or "",
                "comparability_judgment": self._optional_text(
                    context.get("comparability_judgment")
                )
                or request.policy_learning_evidence_admission.comparability_judgment
                or "",
                "commercial_interpretability_summary": self._optional_text(
                    context.get("commercial_interpretability_summary")
                )
                or request.policy_learning_evidence_admission.commercial_interpretability_summary
                or "",
                "proposed_update_scope": self._optional_text(
                    context.get("proposed_update_scope")
                )
                or request.policy_learning_evidence_admission.proposed_update_scope
                or "",
                "comparable_case_set_reference": self._optional_text(
                    context.get("comparable_case_set_reference")
                )
                or request.policy_learning_evidence_admission.comparable_case_set_reference
                or "",
                "restriction_summary": self._optional_text(
                    context.get("restriction_summary")
                )
                or request.policy_learning_evidence_admission.restriction_summary
                or "",
                "memory_object_reference": self._optional_text(
                    context.get("memory_object_reference")
                )
                or request.policy_learning_evidence_admission.memory_object_reference
                or "",
                "evidence_base_summary": self._optional_text(
                    context.get("evidence_base_summary")
                )
                or request.policy_learning_evidence_admission.commercial_interpretability_summary
                or "",
                "policy_behavior_change": self._optional_text(
                    context.get("policy_behavior_change")
                )
                or self._optional_text(context.get("candidate_update_direction"))
                or "",
                "update_scope": self._optional_text(context.get("update_scope"))
                or self._optional_text(context.get("proposed_update_scope"))
                or "",
                "unresolved_competing_explanations": (
                    context.get("unresolved_competing_explanations")
                    or request.policy_learning_evidence_admission.competing_explanations
                    or ()
                ),
                "evidence_gaps": (
                    context.get("evidence_gaps")
                    or request.policy_learning_evidence_admission.evidence_gaps
                    or ()
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

    def _prohibited_update_threshold_fields_present(
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

    def _threshold_status(
        self,
        *,
        policy_learning_evidence_admission: PolicyLearningEvidenceAdmissionRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_update_threshold_fields: tuple[str, ...],
        prohibited_update_threshold_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_update_threshold_fields_present:
            return "prohibited_overlap_blocked"
        if missing_update_threshold_fields:
            return "blocked_missing_context"
        if self._below_threshold(
            policy_learning_evidence_admission,
            class_definition,
            combined_context,
        ):
            return "blocked_below_threshold"
        if fallback_template_used:
            return "fallback_template_applied"
        return "threshold_met"

    def _below_threshold(
        self,
        policy_learning_evidence_admission: PolicyLearningEvidenceAdmissionRecord,
        class_definition,
        combined_context: Mapping[str, object],
    ) -> bool:
        if (
            policy_learning_evidence_admission.policy_learning_evidence_admission_status
            not in class_definition.allowed_policy_learning_evidence_statuses
        ):
            return True
        if (
            policy_learning_evidence_admission.policy_learning_evidence_admission_outcome
            not in class_definition.allowed_policy_learning_evidence_outcomes
        ):
            return True
        if self._policy_learning_evidence_sufficiency_rank(
            policy_learning_evidence_admission.evidence_sufficiency
        ) < self._policy_learning_evidence_sufficiency_rank(
            class_definition.minimum_policy_learning_evidence_sufficiency
        ):
            return True
        if self._policy_learning_evidence_attribution_readiness_rank(
            policy_learning_evidence_admission.attribution_readiness
        ) < self._policy_learning_evidence_attribution_readiness_rank(
            class_definition.minimum_policy_learning_evidence_attribution_readiness
        ):
            return True

        dimension_rank = self._dimension_strength_rank_from_context(combined_context)
        required_dimension_rank = self._dimension_strength_rank(
            class_definition.minimum_dimension_strength
        )
        if not class_definition.allow_monitoring_deferral:
            required_dimension_rank = max(
                required_dimension_rank,
                self._required_dimension_rank_for_severity(
                    self._optional_text(combined_context.get("update_severity"))
                ),
            )
            if self._optional_text(combined_context.get("governance_sensitivity")) == "high":
                required_dimension_rank = max(required_dimension_rank, 2)
        if dimension_rank < required_dimension_rank:
            return True

        repetition_rank = self._repetition_posture_rank(
            self._optional_text(combined_context.get("repetition_posture")) or ""
        )
        required_repetition_rank = self._repetition_posture_rank(
            class_definition.minimum_repetition_posture
        )
        if not class_definition.allow_monitoring_deferral:
            required_repetition_rank = max(
                required_repetition_rank,
                self._required_repetition_rank_for_severity(
                    self._optional_text(combined_context.get("update_severity"))
                ),
            )
        if repetition_rank < required_repetition_rank:
            return True

        if (
            self._optional_text(combined_context.get("commercial_significance"))
            == "low"
            and not class_definition.allow_monitoring_deferral
        ):
            return True

        local_contradiction_posture = self._optional_text(
            combined_context.get("local_contradiction_posture")
        )
        if (
            local_contradiction_posture
            in {
                "local_scope_contradiction_requires_narrowing",
                "material_transfer_contradiction",
            }
            and not class_definition.allow_local_scope_narrowing
        ):
            return True

        unresolved_competing_explanations = self._sequence_as_tuple(
            combined_context.get("unresolved_competing_explanations")
        )
        if (
            unresolved_competing_explanations
            and not class_definition.allow_monitoring_deferral
        ):
            return True

        return False

    def _decision_outcome(
        self,
        *,
        template,
        threshold_status: str,
    ) -> str:
        if threshold_status in {
            "blocked_missing_context",
            "blocked_below_threshold",
            "prohibited_overlap_blocked",
        }:
            return _BLOCKED_OUTCOME
        return template.policy_learning_update_decision_outcome

    def _evidence_sufficiency(
        self,
        *,
        threshold_status: str,
        decision_outcome: str,
    ) -> str:
        if threshold_status == "threshold_met":
            return "sufficient_for_proposed_update"
        if threshold_status == "fallback_template_applied":
            if decision_outcome == "accepted_with_narrowed_scope":
                return "sufficient_only_for_narrowed_scope"
            return "insufficient_pending_more_evidence"
        if threshold_status == "blocked_missing_context":
            return "threshold_evidence_incomplete"
        if threshold_status == "prohibited_overlap_blocked":
            return "threshold_evidence_overlap_prohibited"
        return "insufficient_for_update_threshold"

    def _weak_evidence_check(
        self,
        *,
        threshold_status: str,
        decision_outcome: str,
    ) -> str:
        if threshold_status == "threshold_met":
            return "weak_evidence_check_passed"
        if threshold_status == "fallback_template_applied":
            if decision_outcome == "accepted_with_narrowed_scope":
                return "weak_evidence_check_requires_narrowing"
            return "weak_evidence_check_requires_monitoring"
        if threshold_status == "prohibited_overlap_blocked":
            return "weak_evidence_check_blocked_for_overlap"
        return "weak_evidence_check_failed"

    def _reason(
        self,
        *,
        policy_learning_evidence_admission: PolicyLearningEvidenceAdmissionRecord,
        threshold_status: str,
        policy_learning_update_threshold_class_id: str,
        missing_update_threshold_fields: tuple[str, ...],
        prohibited_update_threshold_fields_present: tuple[str, ...],
        class_definition,
    ) -> str:
        if threshold_status == "blocked_missing_context":
            return (
                "Policy-learning update-threshold review is missing required threshold fields: "
                + ", ".join(missing_update_threshold_fields)
                + "."
            )
        if threshold_status == "prohibited_overlap_blocked":
            return (
                "Policy-learning update-threshold class "
                f"'{policy_learning_update_threshold_class_id}' cannot carry policy mutation, "
                "model retraining, deployment, monitoring, reopen, orchestration, or lifecycle fields: "
                + ", ".join(prohibited_update_threshold_fields_present)
                + "."
            )
        if threshold_status == "blocked_below_threshold":
            return (
                "Policy-learning update-threshold class "
                f"'{policy_learning_update_threshold_class_id}' rejected the admitted evidence "
                "because evidence strength, repetition, scope transfer, or unresolved competing explanations remain below the governed threshold. "
                "Required minimums are evidence_status in "
                f"{class_definition.allowed_policy_learning_evidence_statuses}, evidence_outcome in "
                f"{class_definition.allowed_policy_learning_evidence_outcomes}, evidence_sufficiency>="
                f"{class_definition.minimum_policy_learning_evidence_sufficiency}, attribution_readiness>="
                f"{class_definition.minimum_policy_learning_evidence_attribution_readiness}, dimension_strength>="
                f"{class_definition.minimum_dimension_strength}, and repetition_posture>="
                f"{class_definition.minimum_repetition_posture}. Current upstream status is "
                f"'{policy_learning_evidence_admission.policy_learning_evidence_admission_status}' with outcome "
                f"'{policy_learning_evidence_admission.policy_learning_evidence_admission_outcome}'."
            )
        if threshold_status == "fallback_template_applied":
            if class_definition.allow_local_scope_narrowing:
                return (
                    "A governed fallback update-threshold template accepted the change only within a narrower scope because local contradiction, transfer limits, or update severity block broader policy transfer."
                )
            return (
                "A governed fallback update-threshold template deferred adaptation for continued monitoring because the admitted evidence remains meaningful but not yet strong enough for current policy change."
            )
        return (
            "Policy-learning update-threshold review is complete and the admitted evidence is strong enough to justify the proposed update within the approved scope."
        )

    def _lineage(
        self,
        request: PolicyLearningUpdateThresholdRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.policy_learning_evidence_admission.lineage)
        lineage.update(
            {
                "policy_learning_evidence_admission_id": (
                    request.policy_learning_evidence_admission.policy_learning_evidence_admission_id
                ),
                "policy_learning_evidence_class_id": (
                    request.policy_learning_evidence_admission.policy_learning_evidence_class_id
                ),
                "policy_learning_evidence_template_id": (
                    request.policy_learning_evidence_admission.policy_learning_evidence_template_id
                ),
                "policy_learning_update_threshold_class_id": (
                    class_definition.policy_learning_update_threshold_class_id
                ),
                "policy_learning_update_threshold_class_version": (
                    class_definition.lineage.get("version", "unknown")
                ),
                "policy_learning_update_threshold_template_id": (
                    template.policy_learning_update_threshold_template_id
                ),
                "policy_learning_update_threshold_template_version": (
                    template.lineage.get("version", "unknown")
                ),
            }
        )
        return lineage

    def _policy_learning_evidence_sufficiency_rank(
        self,
        evidence_sufficiency: str,
    ) -> int:
        return _POLICY_LEARNING_EVIDENCE_SUFFICIENCY_RANK.get(evidence_sufficiency, -1)

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

    def _policy_learning_evidence_attribution_readiness_rank(
        self,
        attribution_readiness: str,
    ) -> int:
        return _POLICY_LEARNING_EVIDENCE_ATTRIBUTION_READINESS_RANK.get(
            attribution_readiness,
            -1,
        )

    def _dimension_strength_rank(self, dimension_strength: str) -> int:
        return _DIMENSION_STRENGTH_RANK.get(dimension_strength, -1)

    def _dimension_strength_rank_from_context(
        self,
        context: Mapping[str, object],
    ) -> int:
        if not _DIMENSION_FIELDS:
            return -1
        return min(
            self._dimension_strength_rank(
                self._optional_text(context.get(field_name)) or ""
            )
            for field_name in _DIMENSION_FIELDS
        )

    def _repetition_posture_rank(self, repetition_posture: str) -> int:
        return _REPETITION_POSTURE_RANK.get(repetition_posture, -1)

    def _required_dimension_rank_for_severity(
        self,
        update_severity: str | None,
    ) -> int:
        if update_severity is None:
            return -1
        return _UPDATE_SEVERITY_DIMENSION_RANK.get(update_severity, -1)

    def _required_repetition_rank_for_severity(
        self,
        update_severity: str | None,
    ) -> int:
        if update_severity is None:
            return -1
        return _UPDATE_SEVERITY_REPETITION_RANK.get(update_severity, -1)

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
            return tuple(
                self._to_text(item) for item in value if item not in {None, ""}
            )
        return (self._to_text(value),)

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
