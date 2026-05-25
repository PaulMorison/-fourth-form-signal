from __future__ import annotations

"""Deterministic review-resolution and disposition mapping for ready packets.

Canon ownership:
- Converts governed human-review packets plus explicit reviewer context into
  governed review outcomes and explicit case-disposition classes.
- Owns resolution completeness, disposition mapping, and resolution lineage.
- Does not own packet legitimacy, recommendation generation, escalation
  workflow control, action-instruction issuance, or reopen logic.
"""

from dataclasses import dataclass
from typing import Mapping
from uuid import uuid4

from decision.review.human_review_packet_builder import HumanReviewPacket
from decision.review.review_resolution_audit_adapter import ReviewResolutionAuditAdapter
from decision.review.review_resolution_registry import ReviewResolutionRegistry


@dataclass(frozen=True)
class ReviewResolutionRequest:
    packet: HumanReviewPacket
    resolution_class_id: str
    reviewer_role: str
    resolution_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ReviewResolutionRecord:
    resolution_id: str
    resolution_status: str
    reason: str
    resolution_class_id: str
    disposition_class_id: str
    resolution_state: str
    review_outcome: str
    disposition_state: str
    closure_state: str
    closure_quality: str
    terminality: bool
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
    required_resolution_fields: tuple[str, ...]
    optional_resolution_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    required_resolution_snapshot: Mapping[str, str]
    optional_resolution_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    route_name: str | None = None
    threshold_id: str | None = None
    trigger_class: str | None = None
    playbook_reference: str | None = None
    recommendation_reference: str | None = None
    reopen_reference: str | None = None
    missing_resolution_fields: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "resolution_id": self.resolution_id,
            "resolution_status": self.resolution_status,
            "reason": self.reason,
            "resolution_class_id": self.resolution_class_id,
            "disposition_class_id": self.disposition_class_id,
            "resolution_state": self.resolution_state,
            "review_outcome": self.review_outcome,
            "disposition_state": self.disposition_state,
            "closure_state": self.closure_state,
            "closure_quality": self.closure_quality,
            "terminality": self.terminality,
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
            "required_resolution_fields": list(self.required_resolution_fields),
            "optional_resolution_fields": list(self.optional_resolution_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "required_resolution_snapshot": dict(self.required_resolution_snapshot),
            "optional_resolution_snapshot": dict(self.optional_resolution_snapshot),
            "required_audit_snapshot": dict(self.required_audit_snapshot),
            "lineage": dict(self.lineage),
        }
        if self.route_name is not None:
            payload["route_name"] = self.route_name
        if self.threshold_id is not None:
            payload["threshold_id"] = self.threshold_id
        if self.trigger_class is not None:
            payload["trigger_class"] = self.trigger_class
        if self.playbook_reference is not None:
            payload["playbook_reference"] = self.playbook_reference
        if self.recommendation_reference is not None:
            payload["recommendation_reference"] = self.recommendation_reference
        if self.reopen_reference is not None:
            payload["reopen_reference"] = self.reopen_reference
        if self.missing_resolution_fields:
            payload["missing_resolution_fields"] = list(self.missing_resolution_fields)
        return payload


class ReviewResolutionService:
    """Resolves ready human-review packets into governed review outcomes."""

    def __init__(
        self,
        *,
        review_resolution_registry: ReviewResolutionRegistry,
        review_resolution_audit_adapter: ReviewResolutionAuditAdapter,
    ) -> None:
        self._review_resolution_registry = review_resolution_registry
        self._review_resolution_audit_adapter = review_resolution_audit_adapter

    def resolve(self, request: ReviewResolutionRequest) -> ReviewResolutionRecord:
        resolution_class = self._review_resolution_registry.get_resolution_class(
            request.resolution_class_id
        )
        disposition_class = self._review_resolution_registry.get_disposition_class(
            resolution_class.disposition_class_id
        )
        combined_context = self._combined_context(request)
        required_resolution_snapshot, missing_resolution_fields = self._snapshot_required_fields(
            resolution_class.required_resolution_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            resolution_class.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_resolution_fields + missing_audit_fields)
        )
        optional_resolution_snapshot = self._snapshot_optional_fields(
            resolution_class.optional_resolution_fields,
            combined_context,
        )

        packet_status_allowed = request.packet.packet_status in resolution_class.allowed_packet_statuses
        handoff_ready = request.packet.handoff_ready and request.packet.packet_status != "blocked"
        resolution_status = self._resolution_status(
            packet=request.packet,
            disposition_terminality=disposition_class.terminality,
            missing_fields=all_missing_fields,
            packet_status_allowed=packet_status_allowed,
            handoff_ready=handoff_ready,
        )
        reason = self._resolution_reason(
            packet=request.packet,
            resolution_status=resolution_status,
            resolution_class_id=resolution_class.resolution_class_id,
            allowed_packet_statuses=resolution_class.allowed_packet_statuses,
            missing_fields=all_missing_fields,
        )
        recommendation_reference = self._optional_text(
            request.resolution_context.get("recommendation_reference")
        )

        resolution = ReviewResolutionRecord(
            resolution_id=str(uuid4()),
            resolution_status=resolution_status,
            reason=reason,
            resolution_class_id=resolution_class.resolution_class_id,
            disposition_class_id=disposition_class.disposition_class_id,
            resolution_state=resolution_class.resolution_state,
            review_outcome=resolution_class.review_outcome,
            disposition_state=disposition_class.disposition_state,
            closure_state=disposition_class.closure_state,
            closure_quality=disposition_class.closure_quality,
            terminality=disposition_class.terminality,
            packet_id=request.packet.packet_id,
            packet_template_id=request.packet.packet_template_id,
            packet_status=request.packet.packet_status,
            handoff_ready=request.packet.handoff_ready,
            semantic_scope=request.packet.semantic_scope,
            case_type=request.packet.case_type,
            case_key=request.packet.case_key,
            state_model_name=request.packet.state_model_name,
            episode_id=request.packet.episode_id,
            transition_name=request.packet.transition_name,
            transition_class=request.packet.transition_class,
            source_stage=request.packet.source_stage,
            target_stage=request.packet.target_stage,
            reviewer_role=request.reviewer_role,
            reviewer_id=request.actor_id,
            authority_resolution_kind=request.packet.authority_resolution_kind,
            authority_review_required=request.packet.authority_review_required,
            router_rule_id=request.packet.router_rule_id,
            routing_resolution_status=request.packet.routing_resolution_status,
            routing_review_required=request.packet.routing_review_required,
            review_mode=request.packet.review_mode,
            reason_class=request.packet.reason_class,
            packet_scope=request.packet.packet_scope,
            handoff_channel=request.packet.handoff_channel,
            handoff_purpose=request.packet.handoff_purpose,
            required_resolution_fields=resolution_class.required_resolution_fields,
            optional_resolution_fields=resolution_class.optional_resolution_fields,
            required_audit_fields=resolution_class.required_audit_fields,
            required_resolution_snapshot=required_resolution_snapshot,
            optional_resolution_snapshot=optional_resolution_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(request, resolution_class, disposition_class),
            route_name=request.packet.route_name,
            threshold_id=request.packet.threshold_id,
            trigger_class=request.packet.trigger_class,
            playbook_reference=request.packet.playbook_reference,
            recommendation_reference=recommendation_reference,
            reopen_reference=disposition_class.reopen_reference,
            missing_resolution_fields=all_missing_fields,
        )
        self._review_resolution_audit_adapter.record_resolution(resolution, request=request)
        return resolution

    def _combined_context(self, request: ReviewResolutionRequest) -> dict[str, object]:
        context = dict(request.resolution_context)
        context.update(
            {
                "reviewer_id": request.actor_id,
                "reviewer_role": request.reviewer_role,
                "packet_id": request.packet.packet_id,
                "packet_template_id": request.packet.packet_template_id,
                "packet_status": request.packet.packet_status,
                "case_key": request.packet.case_key,
                "transition_name": request.packet.transition_name,
                "transition_class": request.packet.transition_class,
                "route_name": request.packet.route_name or "",
                "threshold_id": request.packet.threshold_id or "",
                "trigger_class": request.packet.trigger_class or "",
                "playbook_reference": request.packet.playbook_reference or "",
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

    def _resolution_status(
        self,
        *,
        packet: HumanReviewPacket,
        disposition_terminality: bool,
        missing_fields: tuple[str, ...],
        packet_status_allowed: bool,
        handoff_ready: bool,
    ) -> str:
        if missing_fields or not packet_status_allowed or not handoff_ready:
            return "blocked"
        if packet.packet_status == "fallback_template_applied":
            return "fallback_applied"
        if disposition_terminality:
            return "resolved"
        return "ready_for_disposition"

    def _resolution_reason(
        self,
        *,
        packet: HumanReviewPacket,
        resolution_status: str,
        resolution_class_id: str,
        allowed_packet_statuses: tuple[str, ...],
        missing_fields: tuple[str, ...],
    ) -> str:
        if packet.packet_status not in allowed_packet_statuses:
            return (
                f"Packet status '{packet.packet_status}' is not allowed for review resolution class "
                f"'{resolution_class_id}'."
            )
        if not packet.handoff_ready or packet.packet_status == "blocked":
            return "Human review packet is not ready for governed review resolution."
        if missing_fields:
            return (
                "Review resolution is missing required context fields: "
                + ", ".join(missing_fields)
                + "."
            )
        if resolution_status == "fallback_applied":
            return "Fallback review resolution was applied to a fallback review packet."
        if resolution_status == "resolved":
            return "Review resolution fixed a terminal case disposition."
        return "Review resolution fixed a non-terminal disposition and is ready for downstream case handling."

    def _lineage(
        self,
        request: ReviewResolutionRequest,
        resolution_class,
        disposition_class,
    ) -> dict[str, str]:
        lineage = {
            "packet_id": request.packet.packet_id,
            "packet_template_id": request.packet.packet_template_id,
            "packet_status": request.packet.packet_status,
            "resolution_class_id": resolution_class.resolution_class_id,
            "disposition_class_id": disposition_class.disposition_class_id,
            "router_rule_id": request.packet.router_rule_id,
            "authority_resolution_kind": request.packet.authority_resolution_kind,
            "reason_class": request.packet.reason_class,
        }
        if request.packet.route_name is not None:
            lineage["route_name"] = request.packet.route_name
        if request.packet.threshold_id is not None:
            lineage["threshold_id"] = request.packet.threshold_id
        if request.packet.trigger_class is not None:
            lineage["trigger_class"] = request.packet.trigger_class
        if request.packet.playbook_reference is not None:
            lineage["playbook_reference"] = request.packet.playbook_reference
        return lineage

    def _optional_text(self, value: object | None) -> str | None:
        if value is None or value == "":
            return None
        return self._to_text(value)

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)