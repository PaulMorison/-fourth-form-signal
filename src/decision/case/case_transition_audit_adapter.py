from __future__ import annotations

"""Structured transition-audit emission for governed lifecycle outcomes.

Canon ownership:
- Emits lifecycle transition audit events without collapsing them into
  orchestration or routing meaning.
- Keeps accepted, blocked, invalid, fallback, and resumed transition outcomes
  explicit and reconstructible.
"""

from typing import Any

from decision.router.router_service import RouterResolution
from ff_platform.audit.audit_event_store import AuditEventStore
from state.lifecycle.transition_validator import TransitionEvaluation


class CaseTransitionAuditAdapter:
    """Emits structured audit events for every governed transition outcome."""

    _EVENT_TYPE_BY_OUTCOME = {
        "accepted": "decision.case.transition_accepted",
        "blocked": "decision.case.transition_blocked",
        "invalid": "decision.case.transition_invalid",
        "fallback": "decision.case.transition_fallback",
        "resumed": "decision.case.transition_resumed",
    }

    def __init__(self, audit_event_store: AuditEventStore) -> None:
        self._audit_event_store = audit_event_store

    def record_transition_outcome(
        self,
        evaluation: TransitionEvaluation,
        *,
        correlation_id: str,
        episode_id: str,
        actor_id: str,
        reason: str,
        router_resolution: RouterResolution | None = None,
    ) -> None:
        event_type = self._EVENT_TYPE_BY_OUTCOME[evaluation.outcome_kind]
        payload: dict[str, Any] = {
            "transition_name": evaluation.transition_name,
            "state_model_name": evaluation.state_model_name,
            "from_state": evaluation.from_state,
            "to_state": evaluation.to_state,
            "transition_class": evaluation.transition_class,
            "router_rule_id": evaluation.router_rule_id,
            "authority_rule_id": evaluation.authority_rule_id,
            "actor_role": evaluation.actor_role,
            "authority_resolution_kind": evaluation.authority_resolution_kind,
            "resulting_status": evaluation.resulting_status,
            "review_required": evaluation.review_required,
            "transition_reason": reason,
            "validation_reason": evaluation.reason,
        }
        if evaluation.resolved_role is not None:
            payload["resolved_role"] = evaluation.resolved_role
        if evaluation.grant_source_role is not None:
            payload["grant_source_role"] = evaluation.grant_source_role
        if router_resolution is not None:
            payload.update(
                {
                    "routing_conflict_class": router_resolution.conflict_class,
                    "routing_classification_kind": router_resolution.classification_kind,
                    "routing_candidate_count": router_resolution.candidate_count,
                    "routing_resolution_status": router_resolution.resolution_status,
                    "routing_review_required": router_resolution.review_required,
                    "routing_reason": router_resolution.reason,
                    "routing_source_stage": router_resolution.source_stage,
                    "routing_target_stage": router_resolution.target_stage,
                }
            )
            if router_resolution.route_name is not None:
                payload["route_name"] = router_resolution.route_name
            if router_resolution.precedence_rank is not None:
                payload["routing_precedence_rank"] = router_resolution.precedence_rank
            if router_resolution.tie_break_policy is not None:
                payload["routing_tie_break_policy"] = router_resolution.tie_break_policy
            if router_resolution.fallback_route_name is not None:
                payload["routing_fallback_route_name"] = router_resolution.fallback_route_name
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="decision.case.case_transition_audit_adapter",
            correlation_id=correlation_id,
            entity_type="case_episode",
            entity_id=episode_id,
            actor_id=actor_id,
            payload=payload,
            tags=("case-transition", evaluation.transition_class, evaluation.outcome_kind),
        )
