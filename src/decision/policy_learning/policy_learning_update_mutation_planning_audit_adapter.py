from __future__ import annotations

"""Structured audit emission for governed policy-learning update mutation planning.

Canon ownership:
- Emits explicit update-mutation-planning recorded, blocked, ready,
  ready-with-restrictions, deferred, rejected, missing-context,
  prohibited-overlap, and fallback audit events.
- Keeps policy mutation execution, rollout, deployment, retraining,
  monitoring, reopen handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.policy_learning.policy_learning_update_mutation_planning_service import (
        PolicyLearningUpdateMutationPlanningRecord,
        PolicyLearningUpdateMutationPlanningRequest,
    )


class PolicyLearningUpdateMutationPlanningAuditAdapter:
    """Emits governed audit events for policy-learning update mutation planning."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_policy_learning_update_mutation_planning(
        self,
        policy_learning_update_mutation_planning: "PolicyLearningUpdateMutationPlanningRecord",
        *,
        request: "PolicyLearningUpdateMutationPlanningRequest",
    ) -> None:
        payload = policy_learning_update_mutation_planning.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "policy_learning_update_mutation_planning_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_preparation.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = (
            policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_status
        )
        if status in {
            "blocked_missing_context",
            "rejected_for_mutation_planning_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_planning_blocked",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_mutation_planning_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_mutation_planning_use":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_mutation_planning_rejected_for_mutation_planning_use",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                        "rejected-for-mutation-planning-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_mutation_planning_prohibited_overlap_blocked",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="decision.policy_learning.policy_learning_update_mutation_planning_recorded",
            payload=payload,
            request=request,
            tags=(
                "policy-learning",
                policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                "recorded",
            ),
        )

        outcome = (
            policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_outcome
        )
        if outcome == "ready_for_policy_mutation_planning":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_planning_ready_for_policy_mutation_planning",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                    "ready-for-policy-mutation-planning",
                ),
            )
        elif outcome == "ready_for_policy_mutation_planning_with_restrictions":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_planning_ready_for_policy_mutation_planning_with_restrictions",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                    "ready-for-policy-mutation-planning-with-restrictions",
                ),
            )
        elif outcome == "deferred_pending_mutation_planning_prerequisites":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_planning_deferred_pending_mutation_planning_prerequisites",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                    "deferred-pending-mutation-planning-prerequisites",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_planning_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PolicyLearningUpdateMutationPlanningRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner=(
                "decision.policy_learning.policy_learning_update_mutation_planning_audit_adapter"
            ),
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_preparation.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )