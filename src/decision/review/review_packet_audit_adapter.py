from __future__ import annotations

"""Structured audit emission for governed human review packet outcomes.

Canon ownership:
- Emits explicit packet-build, packet-block, and ready-for-handoff audit events.
- Keeps review resolution, escalation posture, and downstream action meaning out
  of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.review.human_review_packet_builder import HumanReviewPacket, HumanReviewPacketBuildRequest


class ReviewPacketAuditAdapter:
    """Emits governed audit events for human review packet outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_packet(
        self,
        packet: "HumanReviewPacket",
        *,
        request: "HumanReviewPacketBuildRequest",
    ) -> None:
        payload = packet.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "human_review_packet",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if packet.packet_status == "blocked":
            self._emit(
                event_type="decision.review.human_review_packet_build_blocked",
                payload=payload,
                request=request,
                tags=("human-review-packet", packet.review_mode, "blocked"),
            )
            if packet.missing_context_fields:
                self._emit(
                    event_type="decision.review.human_review_packet_missing_context",
                    payload=payload,
                    request=request,
                    tags=("human-review-packet", packet.review_mode, "missing-context"),
                )
            return

        self._emit(
            event_type="decision.review.human_review_packet_built",
            payload=payload,
            request=request,
            tags=("human-review-packet", packet.review_mode, "built"),
        )
        self._emit(
            event_type="decision.review.human_review_packet_ready_for_handoff",
            payload=payload,
            request=request,
            tags=("human-review-packet", packet.review_mode, packet.packet_status),
        )
        if packet.packet_status == "fallback_template_applied":
            self._emit(
                event_type="decision.review.human_review_packet_fallback_template_applied",
                payload=payload,
                request=request,
                tags=("human-review-packet", packet.review_mode, "fallback-template"),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "HumanReviewPacketBuildRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="decision.review.review_packet_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )