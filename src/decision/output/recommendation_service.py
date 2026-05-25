from __future__ import annotations

"""Deterministic recommendation-record generation after review resolution.

Canon ownership:
- Converts legitimate review-resolution outputs plus explicit recommendation
  context into governed recommendation records.
- Owns recommendation completeness, advisory posture, lineage, and audit trace.
- Does not own playbook execution, instruction meaning, commitment issuance,
  policy-output generation, reopen meaning, router meaning, or authority meaning.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping
from uuid import uuid4

from decision.output.recommendation_audit_adapter import RecommendationAuditAdapter
from decision.output.recommendation_registry import RecommendationRegistry
from decision.review.review_resolution_service import ReviewResolutionRecord


@dataclass(frozen=True)
class RecommendationRequest:
    review_resolution: ReviewResolutionRecord
    recommendation_class_id: str
    recommender_role: str
    recommendation_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class RecommendationRecord:
    recommendation_id: str
    recommendation_status: str
    reason: str
    recommendation_class_id: str
    recommendation_template_id: str
    action_class: str
    advisory_posture: str
    advisory_status: str
    commitment_readiness: str
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
    recommended_at: datetime
    route_name: str | None = None
    threshold_id: str | None = None
    trigger_class: str | None = None
    playbook_reference: str | None = None
    missing_context_fields: tuple[str, ...] = ()
    prohibited_context_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "recommendation_id": self.recommendation_id,
            "recommendation_status": self.recommendation_status,
            "reason": self.reason,
            "recommendation_class_id": self.recommendation_class_id,
            "recommendation_template_id": self.recommendation_template_id,
            "action_class": self.action_class,
            "advisory_posture": self.advisory_posture,
            "advisory_status": self.advisory_status,
            "commitment_readiness": self.commitment_readiness,
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
            "recommended_at": self.recommended_at.isoformat(),
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


class RecommendationService:
    """Builds governed recommendation records from legitimate review resolution."""

    def __init__(
        self,
        *,
        recommendation_registry: RecommendationRegistry,
        recommendation_audit_adapter: RecommendationAuditAdapter,
    ) -> None:
        self._recommendation_registry = recommendation_registry
        self._recommendation_audit_adapter = recommendation_audit_adapter

    def recommend(self, request: RecommendationRequest) -> RecommendationRecord:
        recommendation_template, fallback_template_used = (
            self._recommendation_registry.resolve_template(
                semantic_scope=request.review_resolution.semantic_scope,
                resolution_class_id=request.review_resolution.resolution_class_id,
                disposition_class_id=request.review_resolution.disposition_class_id,
                recommendation_class_id=request.recommendation_class_id,
                route_name=request.review_resolution.route_name,
            )
        )
        recommendation_class = self._recommendation_registry.get_recommendation_class(
            request.recommendation_class_id
        )
        combined_context = self._combined_context(request, recommendation_class)
        required_context_snapshot, missing_context_fields = self._snapshot_required_fields(
            recommendation_template.required_context_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            recommendation_template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_context_fields + missing_audit_fields)
        )
        optional_context_snapshot = self._snapshot_optional_fields(
            recommendation_template.optional_context_fields,
            combined_context,
        )
        prohibited_context_fields_present = self._prohibited_context_fields_present(
            recommendation_class.prohibited_context_fields,
            request.recommendation_context,
        )

        recommendation_status = self._recommendation_status(
            review_resolution=request.review_resolution,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
            fallback_template_used=fallback_template_used,
        )
        reason = self._recommendation_reason(
            review_resolution=request.review_resolution,
            recommendation_status=recommendation_status,
            recommendation_class_id=recommendation_class.recommendation_class_id,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
        )

        recommendation = RecommendationRecord(
            recommendation_id=str(uuid4()),
            recommendation_status=recommendation_status,
            reason=reason,
            recommendation_class_id=recommendation_class.recommendation_class_id,
            recommendation_template_id=recommendation_template.recommendation_template_id,
            action_class=recommendation_class.action_class,
            advisory_posture=recommendation_class.advisory_posture,
            advisory_status=(
                "recommendation_withheld"
                if recommendation_status == "blocked"
                else "recommendation_issued"
            ),
            commitment_readiness=recommendation_class.commitment_readiness,
            review_resolution_id=request.review_resolution.resolution_id,
            review_resolution_status=request.review_resolution.resolution_status,
            resolution_class_id=request.review_resolution.resolution_class_id,
            resolution_state=request.review_resolution.resolution_state,
            review_outcome=request.review_resolution.review_outcome,
            disposition_class_id=request.review_resolution.disposition_class_id,
            disposition_state=request.review_resolution.disposition_state,
            closure_state=request.review_resolution.closure_state,
            closure_quality=request.review_resolution.closure_quality,
            packet_id=request.review_resolution.packet_id,
            packet_template_id=request.review_resolution.packet_template_id,
            packet_status=request.review_resolution.packet_status,
            handoff_ready=request.review_resolution.handoff_ready,
            semantic_scope=request.review_resolution.semantic_scope,
            case_type=request.review_resolution.case_type,
            case_key=request.review_resolution.case_key,
            state_model_name=request.review_resolution.state_model_name,
            episode_id=request.review_resolution.episode_id,
            transition_name=request.review_resolution.transition_name,
            transition_class=request.review_resolution.transition_class,
            source_stage=request.review_resolution.source_stage,
            target_stage=request.review_resolution.target_stage,
            reviewer_role=request.review_resolution.reviewer_role,
            reviewer_id=request.review_resolution.reviewer_id,
            recommender_role=request.recommender_role,
            recommender_id=request.actor_id,
            authority_resolution_kind=request.review_resolution.authority_resolution_kind,
            authority_review_required=request.review_resolution.authority_review_required,
            router_rule_id=request.review_resolution.router_rule_id,
            routing_resolution_status=request.review_resolution.routing_resolution_status,
            routing_review_required=request.review_resolution.routing_review_required,
            review_mode=request.review_resolution.review_mode,
            reason_class=request.review_resolution.reason_class,
            packet_scope=request.review_resolution.packet_scope,
            handoff_channel=request.review_resolution.handoff_channel,
            handoff_purpose=request.review_resolution.handoff_purpose,
            required_context_fields=recommendation_template.required_context_fields,
            optional_context_fields=recommendation_template.optional_context_fields,
            required_audit_fields=recommendation_template.required_audit_fields,
            prohibited_context_fields=recommendation_class.prohibited_context_fields,
            required_context_snapshot=required_context_snapshot,
            optional_context_snapshot=optional_context_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(request, recommendation_class, recommendation_template),
            recommended_at=datetime.now(tz=UTC),
            route_name=request.review_resolution.route_name,
            threshold_id=request.review_resolution.threshold_id,
            trigger_class=request.review_resolution.trigger_class,
            playbook_reference=request.review_resolution.playbook_reference,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
        )
        self._recommendation_audit_adapter.record_recommendation(
            recommendation,
            request=request,
        )
        return recommendation

    def _combined_context(
        self,
        request: RecommendationRequest,
        recommendation_class,
    ) -> dict[str, object]:
        context = dict(request.review_resolution.required_resolution_snapshot)
        context.update(request.review_resolution.optional_resolution_snapshot)
        context.update(request.review_resolution.required_audit_snapshot)
        context.update(dict(request.recommendation_context))
        context.update(
            {
                "recommendation_class_id": recommendation_class.recommendation_class_id,
                "action_class": recommendation_class.action_class,
                "advisory_posture": recommendation_class.advisory_posture,
                "review_resolution_id": request.review_resolution.resolution_id,
                "review_resolution_status": request.review_resolution.resolution_status,
                "resolution_class_id": request.review_resolution.resolution_class_id,
                "disposition_class_id": request.review_resolution.disposition_class_id,
                "packet_id": request.review_resolution.packet_id,
                "packet_template_id": request.review_resolution.packet_template_id,
                "packet_status": request.review_resolution.packet_status,
                "case_key": request.review_resolution.case_key,
                "route_name": request.review_resolution.route_name or "",
                "threshold_id": request.review_resolution.threshold_id or "",
                "trigger_class": request.review_resolution.trigger_class or "",
                "playbook_reference": request.review_resolution.playbook_reference or "",
                "recommender_id": request.actor_id,
                "recommender_role": request.recommender_role,
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

    def _recommendation_status(
        self,
        *,
        review_resolution: ReviewResolutionRecord,
        missing_context_fields: tuple[str, ...],
        prohibited_context_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if review_resolution.resolution_status == "blocked":
            return "blocked"
        if missing_context_fields or prohibited_context_fields_present:
            return "blocked"
        if fallback_template_used:
            return "fallback_template_applied"
        return "ready_for_downstream_use"

    def _recommendation_reason(
        self,
        *,
        review_resolution: ReviewResolutionRecord,
        recommendation_status: str,
        recommendation_class_id: str,
        missing_context_fields: tuple[str, ...],
        prohibited_context_fields_present: tuple[str, ...],
    ) -> str:
        if review_resolution.resolution_status == "blocked":
            return (
                "Recommendation generation requires a legitimate review resolution and cannot proceed "
                f"from resolution status '{review_resolution.resolution_status}'."
            )
        if missing_context_fields:
            return (
                "Recommendation record is missing required context fields: "
                + ", ".join(missing_context_fields)
                + "."
            )
        if prohibited_context_fields_present:
            return (
                f"Recommendation class '{recommendation_class_id}' cannot carry instruction-like or commitment-like context fields: "
                + ", ".join(prohibited_context_fields_present)
                + "."
            )
        if recommendation_status == "fallback_template_applied":
            return (
                "A governed fallback recommendation template was applied because no route-specific recommendation template exists for the legitimate review resolution."
            )
        return "Recommendation record is complete and ready for downstream advisory use."

    def _lineage(
        self,
        request: RecommendationRequest,
        recommendation_class,
        recommendation_template,
    ) -> dict[str, str]:
        lineage = {
            "review_resolution_id": request.review_resolution.resolution_id,
            "resolution_class_id": request.review_resolution.resolution_class_id,
            "disposition_class_id": request.review_resolution.disposition_class_id,
            "packet_id": request.review_resolution.packet_id,
            "packet_template_id": request.review_resolution.packet_template_id,
            "recommendation_class_id": recommendation_class.recommendation_class_id,
            "recommendation_class_version": recommendation_class.lineage.get(
                "version",
                "unknown",
            ),
            "recommendation_template_id": recommendation_template.recommendation_template_id,
            "recommendation_template_version": recommendation_template.lineage.get(
                "version",
                "unknown",
            ),
            "router_rule_id": request.review_resolution.router_rule_id,
            "authority_resolution_kind": request.review_resolution.authority_resolution_kind,
        }
        if request.review_resolution.route_name is not None:
            lineage["route_name"] = request.review_resolution.route_name
        if request.review_resolution.threshold_id is not None:
            lineage["threshold_id"] = request.review_resolution.threshold_id
        if request.review_resolution.trigger_class is not None:
            lineage["trigger_class"] = request.review_resolution.trigger_class
        return lineage

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)