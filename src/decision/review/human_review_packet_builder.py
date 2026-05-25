from __future__ import annotations

"""Deterministic builder for governed human review packets.

Canon ownership:
- Converts governed review-trigger outcomes plus bounded case context into
  explicit human review packets.
- Owns packet sufficiency, packet scope, reason class, and handoff readiness.
- Does not own review-trigger legitimacy, review resolution, escalation
  workflow, recommendation meaning, or action-instruction meaning.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping
from uuid import uuid4

from decision.review.review_packet_audit_adapter import ReviewPacketAuditAdapter
from decision.review.review_packet_registry import ReviewPacketRegistry

if TYPE_CHECKING:
    from decision.review.review_trigger_service import ReviewTriggerDecision


@dataclass(frozen=True)
class HumanReviewPacketBuildRequest:
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    actor_role: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    route_name: str | None
    routing_resolution_status: str
    routing_review_required: bool
    review_decision: "ReviewTriggerDecision"
    packet_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class HumanReviewPacket:
    packet_id: str
    packet_template_id: str
    packet_status: str
    handoff_ready: bool
    reason: str
    review_trigger_reason: str
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    actor_role: str
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
    required_context_snapshot: Mapping[str, str]
    optional_context_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    route_name: str | None = None
    threshold_id: str | None = None
    trigger_class: str | None = None
    playbook_reference: str | None = None
    missing_context_fields: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "packet_id": self.packet_id,
            "packet_template_id": self.packet_template_id,
            "packet_status": self.packet_status,
            "handoff_ready": self.handoff_ready,
            "reason": self.reason,
            "review_trigger_reason": self.review_trigger_reason,
            "semantic_scope": self.semantic_scope,
            "case_type": self.case_type,
            "case_key": self.case_key,
            "state_model_name": self.state_model_name,
            "episode_id": self.episode_id,
            "transition_name": self.transition_name,
            "transition_class": self.transition_class,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "actor_role": self.actor_role,
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
            "required_context_snapshot": dict(self.required_context_snapshot),
            "optional_context_snapshot": dict(self.optional_context_snapshot),
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
        if self.missing_context_fields:
            payload["missing_context_fields"] = list(self.missing_context_fields)
        return payload


class HumanReviewPacketBuilder:
    """Builds review-only packets from governed trigger outcomes."""

    def __init__(
        self,
        *,
        review_packet_registry: ReviewPacketRegistry,
        review_packet_audit_adapter: ReviewPacketAuditAdapter,
    ) -> None:
        self._review_packet_registry = review_packet_registry
        self._review_packet_audit_adapter = review_packet_audit_adapter

    def build(self, request: HumanReviewPacketBuildRequest) -> HumanReviewPacket:
        if not request.review_decision.requires_packet():
            raise ValueError("Human review packets may only be built for required or optional review-trigger outcomes.")
        if request.review_decision.review_mode is None:
            raise ValueError("Review-trigger decision is missing review_mode required for packet construction.")

        template, fallback_template_used = self._review_packet_registry.resolve_template(
            semantic_scope=request.semantic_scope,
            router_rule_id=request.router_rule_id,
            transition_name=request.transition_name,
            route_name=request.route_name,
            review_mode=request.review_decision.review_mode,
            threshold_id=request.review_decision.threshold_id,
        )
        reason_class = self._review_packet_registry.get_reason_class(template.reason_class)
        combined_context = self._combined_context(request)

        required_context_snapshot, missing_context_fields = self._snapshot_required_fields(
            template.required_context_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(dict.fromkeys(missing_context_fields + missing_audit_fields))
        optional_context_snapshot = self._snapshot_optional_fields(
            template.optional_context_fields,
            combined_context,
        )

        packet = HumanReviewPacket(
            packet_id=str(uuid4()),
            packet_template_id=template.packet_template_id,
            packet_status=self._packet_status(fallback_template_used, all_missing_fields),
            handoff_ready=not all_missing_fields,
            reason=self._packet_reason(fallback_template_used, all_missing_fields),
            review_trigger_reason=request.review_decision.reason,
            semantic_scope=request.semantic_scope,
            case_type=request.case_type,
            case_key=request.case_key,
            state_model_name=request.state_model_name,
            episode_id=request.episode_id,
            transition_name=request.transition_name,
            transition_class=request.transition_class,
            source_stage=request.source_stage,
            target_stage=request.target_stage,
            actor_role=request.actor_role,
            authority_resolution_kind=request.authority_resolution_kind,
            authority_review_required=request.authority_review_required,
            router_rule_id=request.router_rule_id,
            routing_resolution_status=request.routing_resolution_status,
            routing_review_required=request.routing_review_required,
            review_mode=request.review_decision.review_mode,
            reason_class=reason_class.reason_class,
            packet_scope=template.packet_scope,
            handoff_channel=template.handoff_channel,
            handoff_purpose=reason_class.handoff_purpose,
            required_context_fields=template.required_context_fields,
            optional_context_fields=template.optional_context_fields,
            required_audit_fields=template.required_audit_fields,
            required_context_snapshot=required_context_snapshot,
            optional_context_snapshot=optional_context_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(template, request),
            route_name=request.route_name,
            threshold_id=request.review_decision.threshold_id,
            trigger_class=request.review_decision.trigger_class,
            playbook_reference=request.review_decision.playbook_reference,
            missing_context_fields=all_missing_fields,
        )
        self._review_packet_audit_adapter.record_packet(packet, request=request)
        return packet

    def _combined_context(self, request: HumanReviewPacketBuildRequest) -> dict[str, object]:
        context = dict(request.packet_context)
        context.update(
            {
                "semantic_scope": request.semantic_scope,
                "case_type": request.case_type,
                "case_key": request.case_key,
                "state_model_name": request.state_model_name,
                "episode_id": request.episode_id,
                "transition_name": request.transition_name,
                "transition_class": request.transition_class,
                "source_stage": request.source_stage,
                "target_stage": request.target_stage,
                "actor_role": request.actor_role,
                "authority_resolution_kind": request.authority_resolution_kind,
                "authority_review_required": request.authority_review_required,
                "router_rule_id": request.router_rule_id,
                "routing_resolution_status": request.routing_resolution_status,
                "routing_review_required": request.routing_review_required,
                "review_mode": request.review_decision.review_mode,
                "threshold_id": request.review_decision.threshold_id or "",
                "trigger_class": request.review_decision.trigger_class or "",
                "playbook_reference": request.review_decision.playbook_reference or "",
            }
        )
        if request.route_name is not None:
            context["route_name"] = request.route_name
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

    def _packet_status(
        self,
        fallback_template_used: bool,
        missing_context_fields: tuple[str, ...],
    ) -> str:
        if missing_context_fields:
            return "blocked"
        if fallback_template_used:
            return "fallback_template_applied"
        return "ready_for_handoff"

    def _packet_reason(
        self,
        fallback_template_used: bool,
        missing_context_fields: tuple[str, ...],
    ) -> str:
        if missing_context_fields:
            missing = ", ".join(missing_context_fields)
            return f"Human review packet construction blocked because required packet context is missing: {missing}."
        if fallback_template_used:
            return "A governed fallback packet template was applied because no threshold-specific packet template exists for this review outcome."
        return "Human review packet is ready for governed handoff."

    def _lineage(
        self,
        template: object,
        request: HumanReviewPacketBuildRequest,
    ) -> dict[str, str]:
        packet_template = template
        return {
            "packet_template_id": packet_template.packet_template_id,
            "packet_template_version": packet_template.lineage.get("version", "unknown"),
            "packet_template_source": packet_template.lineage.get("source", "unknown"),
            "review_mode": request.review_decision.review_mode or "unknown",
            "threshold_id": request.review_decision.threshold_id or "none",
            "trigger_class": request.review_decision.trigger_class or "none",
        }

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)