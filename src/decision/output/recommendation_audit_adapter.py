from __future__ import annotations

"""Structured audit emission for governed recommendation records.

Canon ownership:
- Emits explicit recommendation-record, recommendation-block, missing-context,
  fallback-template, and ready-for-downstream-use audit events.
- Keeps commitment issuance, instruction issuance, playbook execution, and
  policy-output generation out of this slice.
"""

from typing import TYPE_CHECKING

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.output.recommendation_service import (
        RecommendationRecord,
        RecommendationRequest,
    )


class RecommendationAuditAdapter:
    """Emits governed audit events for recommendation outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_recommendation(
        self,
        recommendation: "RecommendationRecord",
        *,
        request: "RecommendationRequest",
    ) -> None:
        payload = recommendation.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "recommendation_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.review_resolution.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if recommendation.recommendation_status == "blocked":
            self._emit(
                event_type="decision.output.recommendation_blocked",
                payload=payload,
                request=request,
                tags=(
                    "recommendation",
                    recommendation.action_class,
                    "blocked",
                ),
            )
            if recommendation.missing_context_fields:
                self._emit(
                    event_type="decision.output.recommendation_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "recommendation",
                        recommendation.action_class,
                        "missing-context",
                    ),
                )
            return

        self._emit(
            event_type="decision.output.recommendation_recorded",
            payload=payload,
            request=request,
            tags=(
                "recommendation",
                recommendation.action_class,
                "recorded",
            ),
        )
        self._emit(
            event_type="decision.output.recommendation_ready_for_downstream_use",
            payload=payload,
            request=request,
            tags=(
                "recommendation",
                recommendation.action_class,
                recommendation.recommendation_status,
            ),
        )
        if recommendation.recommendation_status == "fallback_template_applied":
            self._emit(
                event_type="decision.output.recommendation_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "recommendation",
                    recommendation.action_class,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "RecommendationRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="decision.output.recommendation_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.review_resolution.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )