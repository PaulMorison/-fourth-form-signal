from __future__ import annotations

"""Deterministic policy-output generation after recommendation recording.

Canon ownership:
- Converts legitimate recommendation records plus explicit policy-output
  context into governed policy outputs.
- Owns bounded policy posture, action-boundary legitimacy, promotion-safe use,
  lineage, and audit trace for policy outputs.
- Does not redefine recommendation meaning, issue commitments or instructions,
  execute playbooks, own escalation posture, own state progression, or absorb
  authority meaning.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping
from uuid import uuid4

from decision.output.policy_output_audit_adapter import PolicyOutputAuditAdapter
from decision.output.policy_output_registry import PolicyOutputRegistry
from decision.output.recommendation_service import RecommendationRecord


@dataclass(frozen=True)
class PolicyOutputRequest:
    recommendation: RecommendationRecord
    policy_output_class_id: str
    policy_author_role: str
    policy_output_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class PolicyOutputRecord:
    policy_output_id: str
    policy_output_status: str
    reason: str
    policy_output_class_id: str
    policy_output_template_id: str
    bounded_policy_posture: str
    action_boundary_posture: str
    promotion_safe_use: str
    recommendation_id: str
    recommendation_status: str
    recommendation_class_id: str
    recommendation_template_id: str
    recommendation_action_class: str
    recommendation_advisory_status: str
    recommendation_commitment_readiness: str
    review_resolution_id: str
    review_resolution_status: str
    resolution_class_id: str
    resolution_state: str
    review_outcome: str
    disposition_class_id: str
    disposition_state: str
    closure_state: str
    closure_quality: str
    packet_id: str
    packet_template_id: str
    packet_status: str
    handoff_ready: bool
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    reviewer_role: str
    reviewer_id: str
    recommender_role: str
    recommender_id: str
    policy_author_role: str
    policy_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    reason_class: str
    packet_scope: str
    handoff_channel: str
    handoff_purpose: str
    required_context_fields: tuple[str, ...]
    optional_context_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_context_fields: tuple[str, ...]
    required_context_snapshot: Mapping[str, str]
    optional_context_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    route_name: str | None = None
    threshold_id: str | None = None
    trigger_class: str | None = None
    playbook_reference: str | None = None
    missing_context_fields: tuple[str, ...] = ()
    prohibited_context_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "policy_output_id": self.policy_output_id,
            "policy_output_status": self.policy_output_status,
            "reason": self.reason,
            "policy_output_class_id": self.policy_output_class_id,
            "policy_output_template_id": self.policy_output_template_id,
            "bounded_policy_posture": self.bounded_policy_posture,
            "action_boundary_posture": self.action_boundary_posture,
            "promotion_safe_use": self.promotion_safe_use,
            "recommendation_id": self.recommendation_id,
            "recommendation_status": self.recommendation_status,
            "recommendation_class_id": self.recommendation_class_id,
            "recommendation_template_id": self.recommendation_template_id,
            "recommendation_action_class": self.recommendation_action_class,
            "recommendation_advisory_status": self.recommendation_advisory_status,
            "recommendation_commitment_readiness": self.recommendation_commitment_readiness,
            "review_resolution_id": self.review_resolution_id,
            "review_resolution_status": self.review_resolution_status,
            "resolution_class_id": self.resolution_class_id,
            "resolution_state": self.resolution_state,
            "review_outcome": self.review_outcome,
            "disposition_class_id": self.disposition_class_id,
            "disposition_state": self.disposition_state,
            "closure_state": self.closure_state,
            "closure_quality": self.closure_quality,
            "packet_id": self.packet_id,
            "packet_template_id": self.packet_template_id,
            "packet_status": self.packet_status,
            "handoff_ready": self.handoff_ready,
            "semantic_scope": self.semantic_scope,
            "case_type": self.case_type,
            "case_key": self.case_key,
            "state_model_name": self.state_model_name,
            "episode_id": self.episode_id,
            "transition_name": self.transition_name,
            "transition_class": self.transition_class,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "reviewer_role": self.reviewer_role,
            "reviewer_id": self.reviewer_id,
            "recommender_role": self.recommender_role,
            "recommender_id": self.recommender_id,
            "policy_author_role": self.policy_author_role,
            "policy_author_id": self.policy_author_id,
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "reason_class": self.reason_class,
            "packet_scope": self.packet_scope,
            "handoff_channel": self.handoff_channel,
            "handoff_purpose": self.handoff_purpose,
            "required_context_fields": list(self.required_context_fields),
            "optional_context_fields": list(self.optional_context_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_context_fields": list(self.prohibited_context_fields),
            "required_context_snapshot": dict(self.required_context_snapshot),
            "optional_context_snapshot": dict(self.optional_context_snapshot),
            "required_audit_snapshot": dict(self.required_audit_snapshot),
            "lineage": dict(self.lineage),
            "generated_at": self.generated_at.isoformat(),
        }
        if self.route_name is not None:
            payload["route_name"] = self.route_name
        if self.threshold_id is not None:
            payload["threshold_id"] = self.threshold_id
        if self.trigger_class is not None:
            payload["trigger_class"] = self.trigger_class
        if self.playbook_reference is not None:
            payload["playbook_reference"] = self.playbook_reference
        if self.missing_context_fields:
            payload["missing_context_fields"] = list(self.missing_context_fields)
        if self.prohibited_context_fields_present:
            payload["prohibited_context_fields_present"] = list(
                self.prohibited_context_fields_present
            )
        return payload


class PolicyOutputService:
    """Builds governed policy outputs from legitimate recommendation records."""

    def __init__(
        self,
        *,
        policy_output_registry: PolicyOutputRegistry,
        policy_output_audit_adapter: PolicyOutputAuditAdapter,
    ) -> None:
        self._policy_output_registry = policy_output_registry
        self._policy_output_audit_adapter = policy_output_audit_adapter

    def generate(self, request: PolicyOutputRequest) -> PolicyOutputRecord:
        policy_output_template, fallback_template_used = (
            self._policy_output_registry.resolve_template(
                semantic_scope=request.recommendation.semantic_scope,
                resolution_class_id=request.recommendation.resolution_class_id,
                disposition_class_id=request.recommendation.disposition_class_id,
                recommendation_class_id=request.recommendation.recommendation_class_id,
                policy_output_class_id=request.policy_output_class_id,
                route_name=request.recommendation.route_name,
            )
        )
        policy_output_class = self._policy_output_registry.get_policy_output_class(
            request.policy_output_class_id
        )
        combined_context = self._combined_context(request, policy_output_class)
        required_context_snapshot, missing_context_fields = self._snapshot_required_fields(
            policy_output_template.required_context_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            policy_output_template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_context_fields + missing_audit_fields)
        )
        optional_context_snapshot = self._snapshot_optional_fields(
            policy_output_template.optional_context_fields,
            combined_context,
        )
        prohibited_context_fields_present = self._prohibited_context_fields_present(
            policy_output_class.prohibited_context_fields,
            request.policy_output_context,
        )

        policy_output_status = self._policy_output_status(
            recommendation=request.recommendation,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
            fallback_template_used=fallback_template_used,
        )
        reason = self._policy_output_reason(
            recommendation=request.recommendation,
            policy_output_status=policy_output_status,
            policy_output_class_id=policy_output_class.policy_output_class_id,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
        )

        policy_output = PolicyOutputRecord(
            policy_output_id=str(uuid4()),
            policy_output_status=policy_output_status,
            reason=reason,
            policy_output_class_id=policy_output_class.policy_output_class_id,
            policy_output_template_id=policy_output_template.policy_output_template_id,
            bounded_policy_posture=policy_output_class.bounded_policy_posture,
            action_boundary_posture=policy_output_class.action_boundary_posture,
            promotion_safe_use=policy_output_class.promotion_safe_use,
            recommendation_id=request.recommendation.recommendation_id,
            recommendation_status=request.recommendation.recommendation_status,
            recommendation_class_id=request.recommendation.recommendation_class_id,
            recommendation_template_id=request.recommendation.recommendation_template_id,
            recommendation_action_class=request.recommendation.action_class,
            recommendation_advisory_status=request.recommendation.advisory_status,
            recommendation_commitment_readiness=request.recommendation.commitment_readiness,
            review_resolution_id=request.recommendation.review_resolution_id,
            review_resolution_status=request.recommendation.review_resolution_status,
            resolution_class_id=request.recommendation.resolution_class_id,
            resolution_state=request.recommendation.resolution_state,
            review_outcome=request.recommendation.review_outcome,
            disposition_class_id=request.recommendation.disposition_class_id,
            disposition_state=request.recommendation.disposition_state,
            closure_state=request.recommendation.closure_state,
            closure_quality=request.recommendation.closure_quality,
            packet_id=request.recommendation.packet_id,
            packet_template_id=request.recommendation.packet_template_id,
            packet_status=request.recommendation.packet_status,
            handoff_ready=request.recommendation.handoff_ready,
            semantic_scope=request.recommendation.semantic_scope,
            case_type=request.recommendation.case_type,
            case_key=request.recommendation.case_key,
            state_model_name=request.recommendation.state_model_name,
            episode_id=request.recommendation.episode_id,
            transition_name=request.recommendation.transition_name,
            transition_class=request.recommendation.transition_class,
            source_stage=request.recommendation.source_stage,
            target_stage=request.recommendation.target_stage,
            reviewer_role=request.recommendation.reviewer_role,
            reviewer_id=request.recommendation.reviewer_id,
            recommender_role=request.recommendation.recommender_role,
            recommender_id=request.recommendation.recommender_id,
            policy_author_role=request.policy_author_role,
            policy_author_id=request.actor_id,
            authority_resolution_kind=request.recommendation.authority_resolution_kind,
            authority_review_required=request.recommendation.authority_review_required,
            router_rule_id=request.recommendation.router_rule_id,
            routing_resolution_status=request.recommendation.routing_resolution_status,
            routing_review_required=request.recommendation.routing_review_required,
            review_mode=request.recommendation.review_mode,
            reason_class=request.recommendation.reason_class,
            packet_scope=request.recommendation.packet_scope,
            handoff_channel=request.recommendation.handoff_channel,
            handoff_purpose=request.recommendation.handoff_purpose,
            required_context_fields=policy_output_template.required_context_fields,
            optional_context_fields=policy_output_template.optional_context_fields,
            required_audit_fields=policy_output_template.required_audit_fields,
            prohibited_context_fields=policy_output_class.prohibited_context_fields,
            required_context_snapshot=required_context_snapshot,
            optional_context_snapshot=optional_context_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(request, policy_output_class, policy_output_template),
            generated_at=datetime.now(tz=UTC),
            route_name=request.recommendation.route_name,
            threshold_id=request.recommendation.threshold_id,
            trigger_class=request.recommendation.trigger_class,
            playbook_reference=request.recommendation.playbook_reference,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
        )
        self._policy_output_audit_adapter.record_policy_output(
            policy_output,
            request=request,
        )
        return policy_output

    def _combined_context(
        self,
        request: PolicyOutputRequest,
        policy_output_class,
    ) -> dict[str, object]:
        context = dict(request.recommendation.required_context_snapshot)
        context.update(request.recommendation.optional_context_snapshot)
        context.update(request.recommendation.required_audit_snapshot)
        context.update(dict(request.policy_output_context))
        context.update(
            {
                "policy_output_class_id": policy_output_class.policy_output_class_id,
                "bounded_policy_posture": policy_output_class.bounded_policy_posture,
                "action_boundary_posture": policy_output_class.action_boundary_posture,
                "promotion_safe_use": policy_output_class.promotion_safe_use,
                "recommendation_id": request.recommendation.recommendation_id,
                "recommendation_status": request.recommendation.recommendation_status,
                "recommendation_class_id": request.recommendation.recommendation_class_id,
                "recommendation_template_id": request.recommendation.recommendation_template_id,
                "review_resolution_id": request.recommendation.review_resolution_id,
                "review_resolution_status": request.recommendation.review_resolution_status,
                "resolution_class_id": request.recommendation.resolution_class_id,
                "disposition_class_id": request.recommendation.disposition_class_id,
                "packet_id": request.recommendation.packet_id,
                "packet_template_id": request.recommendation.packet_template_id,
                "packet_status": request.recommendation.packet_status,
                "case_key": request.recommendation.case_key,
                "route_name": request.recommendation.route_name or "",
                "threshold_id": request.recommendation.threshold_id or "",
                "trigger_class": request.recommendation.trigger_class or "",
                "playbook_reference": request.recommendation.playbook_reference or "",
                "policy_author_id": request.actor_id,
                "policy_author_role": request.policy_author_role,
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
            if value is None or value == "":
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
            if value is None or value == "":
                continue
            snapshot[field_name] = self._to_text(value)
        return snapshot

    def _prohibited_context_fields_present(
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

    def _policy_output_status(
        self,
        *,
        recommendation: RecommendationRecord,
        missing_context_fields: tuple[str, ...],
        prohibited_context_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if recommendation.recommendation_status == "blocked":
            return "blocked"
        if missing_context_fields or prohibited_context_fields_present:
            return "blocked"
        if fallback_template_used:
            return "fallback_template_applied"
        return "ready_for_downstream_use"

    def _policy_output_reason(
        self,
        *,
        recommendation: RecommendationRecord,
        policy_output_status: str,
        policy_output_class_id: str,
        missing_context_fields: tuple[str, ...],
        prohibited_context_fields_present: tuple[str, ...],
    ) -> str:
        if recommendation.recommendation_status == "blocked":
            return (
                "Policy output generation requires a legitimate recommendation record and cannot proceed "
                f"from recommendation status '{recommendation.recommendation_status}'."
            )
        if missing_context_fields:
            return (
                "Policy output is missing required context fields: "
                + ", ".join(missing_context_fields)
                + "."
            )
        if prohibited_context_fields_present:
            return (
                f"Policy output class '{policy_output_class_id}' cannot carry instruction-like or commitment-like context fields: "
                + ", ".join(prohibited_context_fields_present)
                + "."
            )
        if policy_output_status == "fallback_template_applied":
            return (
                "A governed fallback policy-output template was applied because no route-specific policy-output template exists for the governed recommendation."
            )
        return "Policy output is complete and ready for downstream governed use."

    def _lineage(
        self,
        request: PolicyOutputRequest,
        policy_output_class,
        policy_output_template,
    ) -> dict[str, str]:
        lineage = {
            "recommendation_id": request.recommendation.recommendation_id,
            "recommendation_class_id": request.recommendation.recommendation_class_id,
            "recommendation_class_version": request.recommendation.lineage.get(
                "recommendation_class_version",
                "unknown",
            ),
            "recommendation_template_id": request.recommendation.recommendation_template_id,
            "recommendation_template_version": request.recommendation.lineage.get(
                "recommendation_template_version",
                "unknown",
            ),
            "review_resolution_id": request.recommendation.review_resolution_id,
            "resolution_class_id": request.recommendation.resolution_class_id,
            "disposition_class_id": request.recommendation.disposition_class_id,
            "packet_id": request.recommendation.packet_id,
            "packet_template_id": request.recommendation.packet_template_id,
            "policy_output_class_id": policy_output_class.policy_output_class_id,
            "policy_output_class_version": policy_output_class.lineage.get(
                "version",
                "unknown",
            ),
            "policy_output_template_id": policy_output_template.policy_output_template_id,
            "policy_output_template_version": policy_output_template.lineage.get(
                "version",
                "unknown",
            ),
            "router_rule_id": request.recommendation.router_rule_id,
            "authority_resolution_kind": request.recommendation.authority_resolution_kind,
        }
        if request.recommendation.route_name is not None:
            lineage["route_name"] = request.recommendation.route_name
        if request.recommendation.threshold_id is not None:
            lineage["threshold_id"] = request.recommendation.threshold_id
        if request.recommendation.trigger_class is not None:
            lineage["trigger_class"] = request.recommendation.trigger_class
        return lineage

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)