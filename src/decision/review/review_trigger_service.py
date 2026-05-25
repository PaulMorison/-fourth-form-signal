from __future__ import annotations

"""Governed review-trigger evaluation for routed decision context.

Canon ownership:
- Evaluates explicit review-entry thresholds after routing succeeds.
- Keeps review execution, escalation workflow, and playbook interpretation out
  of this slice.
"""

from dataclasses import dataclass
from typing import Mapping

from decision.review.review_audit_adapter import ReviewAuditAdapter
from decision.review.threshold_evaluator import ReviewThresholdEvaluation, ThresholdEvaluator
from decision.review.threshold_registry import ReviewThresholdRegistry


@dataclass(frozen=True)
class ReviewTriggerRequest:
    semantic_scope: str
    state_model_name: str
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
    routing_conflict_class: str
    routing_candidate_count: int
    routing_review_required: bool
    decision_context: Mapping[str, object]
    correlation_id: str
    episode_id: str
    actor_id: str


@dataclass(frozen=True)
class ReviewTriggerDecision:
    outcome_kind: str
    reason: str
    semantic_scope: str
    state_model_name: str
    transition_name: str
    router_rule_id: str
    route_name: str | None
    threshold_id: str | None = None
    trigger_class: str | None = None
    review_mode: str | None = None
    calibration_profile_id: str | None = None
    fallback_review_mode: str | None = None
    playbook_reference: str | None = None
    matched_threshold_ids: tuple[str, ...] = ()

    def requires_packet(self) -> bool:
        """Return whether the trigger outcome requires packet construction."""

        return self.outcome_kind in {"required", "optional"}


class ReviewTriggerService:
    """Evaluates governed thresholds and returns the review-trigger outcome."""

    _SEVERITY_ORDER = {"blocked": 3, "required": 2, "optional": 1, "not_triggered": 0}

    def __init__(
        self,
        *,
        threshold_registry: ReviewThresholdRegistry,
        threshold_evaluator: ThresholdEvaluator,
        review_audit_adapter: ReviewAuditAdapter,
    ) -> None:
        self._threshold_registry = threshold_registry
        self._threshold_evaluator = threshold_evaluator
        self._review_audit_adapter = review_audit_adapter

    def evaluate(self, request: ReviewTriggerRequest) -> ReviewTriggerDecision:
        thresholds = sorted(
            self._threshold_registry.find_thresholds(
                semantic_scope=request.semantic_scope,
                router_rule_id=request.router_rule_id,
                transition_name=request.transition_name,
                route_name=request.route_name,
            ),
            key=lambda threshold: threshold.threshold_id,
        )
        context = self._combined_context(request)
        evaluations = tuple(
            self._threshold_evaluator.evaluate(
                threshold,
                context=context,
                routing_review_required=request.routing_review_required,
                authority_review_required=request.authority_review_required,
                calibration_profile=(
                    self._threshold_registry.get_calibration_profile(threshold.calibration_profile_id)
                    if threshold.calibration_profile_id is not None
                    else None
                ),
            )
            for threshold in thresholds
        )
        decision = self._decision_from(request, evaluations)
        self._review_audit_adapter.record_decision(decision, evaluations, request=request)
        return decision

    def _decision_from(
        self,
        request: ReviewTriggerRequest,
        evaluations: tuple[ReviewThresholdEvaluation, ...],
    ) -> ReviewTriggerDecision:
        matched_threshold_ids = tuple(evaluation.threshold_id for evaluation in evaluations)
        if not evaluations:
            return ReviewTriggerDecision(
                outcome_kind="not_triggered",
                reason="No governed review thresholds apply to the routed transition.",
                semantic_scope=request.semantic_scope,
                state_model_name=request.state_model_name,
                transition_name=request.transition_name,
                router_rule_id=request.router_rule_id,
                route_name=request.route_name,
                matched_threshold_ids=matched_threshold_ids,
            )

        primary = sorted(
            evaluations,
            key=lambda evaluation: (
                -self._SEVERITY_ORDER[evaluation.outcome_kind],
                evaluation.threshold_id,
            ),
        )[0]
        if primary.outcome_kind == "not_triggered":
            return ReviewTriggerDecision(
                outcome_kind="not_triggered",
                reason="Applicable review thresholds were evaluated and none triggered review entry.",
                semantic_scope=request.semantic_scope,
                state_model_name=request.state_model_name,
                transition_name=request.transition_name,
                router_rule_id=request.router_rule_id,
                route_name=request.route_name,
                matched_threshold_ids=matched_threshold_ids,
            )

        return ReviewTriggerDecision(
            outcome_kind=primary.outcome_kind,
            reason=primary.reason,
            semantic_scope=request.semantic_scope,
            state_model_name=request.state_model_name,
            transition_name=request.transition_name,
            router_rule_id=request.router_rule_id,
            route_name=request.route_name,
            threshold_id=primary.threshold_id,
            trigger_class=primary.trigger_class,
            review_mode=(primary.outcome_kind if primary.outcome_kind in {"required", "optional"} else None),
            calibration_profile_id=primary.calibration_profile_id,
            fallback_review_mode=primary.fallback_review_mode,
            playbook_reference=primary.playbook_reference,
            matched_threshold_ids=matched_threshold_ids,
        )

    def _combined_context(self, request: ReviewTriggerRequest) -> dict[str, object]:
        context = dict(request.decision_context)
        context.update(
            {
                "transition_name": request.transition_name,
                "transition_class": request.transition_class,
                "source_stage": request.source_stage,
                "target_stage": request.target_stage,
                "actor_role": request.actor_role,
                "authority_resolution_kind": request.authority_resolution_kind,
                "authority_review_required": request.authority_review_required,
                "router_rule_id": request.router_rule_id,
                "route_name": request.route_name or "",
                "routing_resolution_status": request.routing_resolution_status,
                "routing_conflict_class": request.routing_conflict_class,
                "routing_candidate_count": request.routing_candidate_count,
                "routing_review_required": request.routing_review_required,
            }
        )
        return context
