from __future__ import annotations

"""Structured audit emission for governed router outcomes.

Canon ownership:
- Emits governed router events for classification, tie-break, fallback, success,
  blocked routing, and unresolved conflict outcomes.
- Does not decide routing legitimacy, lifecycle legitimacy, or review execution.
"""

from typing import TYPE_CHECKING, Any

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.router.conflict_classifier import RoutingConflictClassification
    from decision.router.router_service import RouterResolution, RouterResolutionRequest


class RouterAuditAdapter:
    """Emits governed audit events for router outcomes."""

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
        resolution: "RouterResolution",
        classification: "RoutingConflictClassification",
        *,
        request: "RouterResolutionRequest",
    ) -> None:
        self._emit_event(
            "decision.router.conflict_classified",
            resolution,
            classification,
            request,
        )
        if resolution.tie_break_applied:
            self._emit_event(
                "decision.router.tie_break_applied",
                resolution,
                classification,
                request,
            )
        if resolution.fallback_route_applied:
            self._emit_event(
                "decision.router.fallback_route_applied",
                resolution,
                classification,
                request,
            )
        if resolution.resolution_status == "unresolved":
            self._emit_event(
                "decision.router.unresolved_conflict_detected",
                resolution,
                classification,
                request,
            )

        event_name = (
            "decision.router.router_resolution_succeeded"
            if resolution.accepted
            else "decision.router.router_resolution_blocked"
        )
        self._emit_event(event_name, resolution, classification, request)

    def _emit_event(
        self,
        event_name: str,
        resolution: "RouterResolution",
        classification: "RoutingConflictClassification",
        request: "RouterResolutionRequest",
    ) -> None:
        payload = self._build_payload(event_name, resolution, classification, request)
        self._contract_validator.validate_or_raise(
            "router_resolution_event",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )
        self._audit_event_store.record_event(
            event_type=event_name,
            owner="decision.router.router_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=("router", resolution.resolution_status, request.transition_class),
        )

    def _build_payload(
        self,
        event_name: str,
        resolution: "RouterResolution",
        classification: "RoutingConflictClassification",
        request: "RouterResolutionRequest",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_name": event_name,
            "router_rule_id": resolution.router_rule_id,
            "semantic_scope": resolution.semantic_scope,
            "state_model_name": request.state_model_name,
            "transition_name": request.transition_name,
            "transition_class": request.transition_class,
            "source_stage": request.source_stage,
            "target_stage": request.target_stage,
            "conflict_class": classification.conflict_class,
            "classification_kind": classification.classification_kind,
            "candidate_count": classification.candidate_count,
            "resolution_status": resolution.resolution_status,
            "review_required": resolution.review_required,
            "reason": resolution.reason,
        }
        if resolution.route_name is not None:
            payload["route_name"] = resolution.route_name
        if resolution.precedence_rank is not None:
            payload["precedence_rank"] = resolution.precedence_rank
        if resolution.tie_break_policy is not None:
            payload["tie_break_policy"] = resolution.tie_break_policy
        if resolution.fallback_route_name is not None:
            payload["fallback_route_name"] = resolution.fallback_route_name
        return payload
