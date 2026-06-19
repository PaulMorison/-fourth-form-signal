from __future__ import annotations

"""Structured audit emission for governed review-threshold outcomes.

Canon ownership:
- Emits explicit threshold-evaluation and review-trigger audit events.
- Does not execute review workflow, escalation workflow, or playbook meaning.
"""

from typing import TYPE_CHECKING, Any

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.review.review_trigger_service import ReviewTriggerDecision, ReviewTriggerRequest
    from decision.review.threshold_evaluator import ReviewThresholdEvaluation


class ReviewAuditAdapter:
    """Emits governed audit events for threshold evaluation and trigger outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_decision(
        self,
        decision: "ReviewTriggerDecision",
        evaluations: tuple["ReviewThresholdEvaluation", ...],
        *,
        request: "ReviewTriggerRequest",
    ) -> None:
        for evaluation in evaluations:
            evaluation_event = (
                "decision.review.threshold_evaluation_blocked"
                if evaluation.outcome_kind == "blocked"
                else "decision.review.threshold_evaluation_succeeded"
            )
            self._emit_event(
                event_name=evaluation_event,
                review_outcome=evaluation.outcome_kind,
                request=request,
                decision=decision,
                evaluation=evaluation,
            )
            if evaluation.calibration_applied:
                self._emit_event(
                    event_name="decision.review.calibration_profile_applied",
                    review_outcome=evaluation.outcome_kind,
                    request=request,
                    decision=decision,
                    evaluation=evaluation,
                )
            if evaluation.fallback_review_mode_applied:
                self._emit_event(
                    event_name="decision.review.fallback_review_mode_applied",
                    review_outcome=evaluation.outcome_kind,
                    request=request,
                    decision=decision,
                    evaluation=evaluation,
                )
            if evaluation.outcome_kind in {"required", "optional"}:
                self._emit_event(
                    event_name="decision.review.threshold_triggered",
                    review_outcome=evaluation.outcome_kind,
                    request=request,
                    decision=decision,
                    evaluation=evaluation,
                )
            elif evaluation.outcome_kind == "not_triggered":
                self._emit_event(
                    event_name="decision.review.threshold_not_triggered",
                    review_outcome=evaluation.outcome_kind,
                    request=request,
                    decision=decision,
                    evaluation=evaluation,
                )

        if decision.outcome_kind == "required":
            self._emit_event(
                event_name="decision.review.review_trigger_required",
                review_outcome=decision.outcome_kind,
                request=request,
                decision=decision,
                evaluation=None,
            )
        elif decision.outcome_kind == "optional":
            self._emit_event(
                event_name="decision.review.review_trigger_optional",
                review_outcome=decision.outcome_kind,
                request=request,
                decision=decision,
                evaluation=None,
            )

    def _emit_event(
        self,
        *,
        event_name: str,
        review_outcome: str,
        request: "ReviewTriggerRequest",
        decision: "ReviewTriggerDecision",
        evaluation: "ReviewThresholdEvaluation | None",
    ) -> None:
        payload = self._build_payload(
            event_name=event_name,
            review_outcome=review_outcome,
            request=request,
            decision=decision,
            evaluation=evaluation,
        )
        self._contract_validator.validate_or_raise(
            "review_trigger_event",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )
        self._audit_event_store.record_event(
            event_type=event_name,
            owner="decision.review.review_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=("review-trigger", review_outcome, request.transition_class),
        )

    def _build_payload(
        self,
        *,
        event_name: str,
        review_outcome: str,
        request: "ReviewTriggerRequest",
        decision: "ReviewTriggerDecision",
        evaluation: "ReviewThresholdEvaluation | None",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_name": event_name,
            "semantic_scope": request.semantic_scope,
            "state_model_name": request.state_model_name,
            "transition_name": request.transition_name,
            "transition_class": request.transition_class,
            "router_rule_id": request.router_rule_id,
            "source_stage": request.source_stage,
            "target_stage": request.target_stage,
            "routing_resolution_status": request.routing_resolution_status,
            "actor_role": request.actor_role,
            "authority_resolution_kind": request.authority_resolution_kind,
            "authority_review_required": request.authority_review_required,
            "routing_review_required": request.routing_review_required,
            "review_outcome": review_outcome,
            "reason": evaluation.reason if evaluation is not None else decision.reason,
        }
        if request.route_name is not None:
            payload["route_name"] = request.route_name
        if evaluation is not None:
            payload["threshold_id"] = evaluation.threshold_id
            payload["trigger_class"] = evaluation.trigger_class
            payload["review_mode"] = evaluation.configured_review_mode
            payload["value_source"] = evaluation.value_source
            payload["comparison_value_text"] = evaluation.comparison_value_text
            payload["required_context_fields"] = list(evaluation.required_context_fields)
            if evaluation.actual_value_text is not None:
                payload["actual_value_text"] = evaluation.actual_value_text
            if evaluation.calibrated_comparison_value_text is not None:
                payload["calibrated_comparison_value_text"] = evaluation.calibrated_comparison_value_text
            if evaluation.calibration_profile_id is not None:
                payload["calibration_profile_id"] = evaluation.calibration_profile_id
            if evaluation.fallback_review_mode is not None:
                payload["fallback_review_mode"] = evaluation.fallback_review_mode
            if evaluation.playbook_reference is not None:
                payload["playbook_reference"] = evaluation.playbook_reference
        else:
            if decision.threshold_id is not None:
                payload["threshold_id"] = decision.threshold_id
            if decision.trigger_class is not None:
                payload["trigger_class"] = decision.trigger_class
            if decision.review_mode is not None:
                payload["review_mode"] = decision.review_mode
            if decision.calibration_profile_id is not None:
                payload["calibration_profile_id"] = decision.calibration_profile_id
            if decision.fallback_review_mode is not None:
                payload["fallback_review_mode"] = decision.fallback_review_mode
            if decision.playbook_reference is not None:
                payload["playbook_reference"] = decision.playbook_reference
        return payload
