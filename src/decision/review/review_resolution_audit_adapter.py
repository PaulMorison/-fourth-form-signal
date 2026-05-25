from __future__ import annotations

"""Structured audit emission for governed review-resolution outcomes.

Canon ownership:
- Emits explicit review-resolution, resolution-block, ready-for-disposition,
  and fallback-resolution audit events.
- Keeps recommendation generation, action-instruction issuance, escalation
  workflow control, and reopen logic out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.review.review_resolution_service import (
        ReviewResolutionRecord,
        ReviewResolutionRequest,
    )


class ReviewResolutionAuditAdapter:
    """Emits governed audit events for review-resolution outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_resolution(
        self,
        resolution: "ReviewResolutionRecord",
        *,
        request: "ReviewResolutionRequest",
    ) -> None:
        payload = resolution.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "review_resolution_event",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.packet.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if resolution.resolution_status == "blocked":
            self._emit(
                event_type="decision.review.review_resolution_blocked",
                payload=payload,
                request=request,
                tags=("review-resolution", resolution.review_outcome, "blocked"),
            )
            if resolution.missing_resolution_fields:
                self._emit(
                    event_type="decision.review.review_resolution_missing_context",
                    payload=payload,
                    request=request,
                    tags=("review-resolution", resolution.review_outcome, "missing-context"),
                )
            return

        self._emit(
            event_type="decision.review.review_resolution_recorded",
            payload=payload,
            request=request,
            tags=("review-resolution", resolution.review_outcome, "recorded"),
        )
        self._emit(
            event_type="decision.review.review_resolution_ready_for_disposition",
            payload=payload,
            request=request,
            tags=("review-resolution", resolution.review_outcome, resolution.resolution_status),
        )
        if resolution.resolution_status == "fallback_applied":
            self._emit(
                event_type="decision.review.review_resolution_fallback_applied",
                payload=payload,
                request=request,
                tags=("review-resolution", resolution.review_outcome, "fallback"),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ReviewResolutionRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="decision.review.review_resolution_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.packet.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )